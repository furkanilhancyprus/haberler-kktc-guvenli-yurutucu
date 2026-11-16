"""Convert an editor-verified story into an idempotent Blob handoff."""
import argparse
import io
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont, ImageOps

from verify_media import DirectOnly, UPLOAD, verify_blob_url, verify_jpeg

ROOT = Path(__file__).resolve().parent
CYPRUS = ZoneInfo("Asia/Famagusta")
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{7,100}")
FONT_PATHS = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("C:/Windows/Fonts/arialbd.ttf"),
)


def checked_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.port not in (None, 443):
        raise ValueError("UNSAFE_SOURCE_URL")
    return url


def load_news(now, requested):
    stories = []
    for path in (ROOT / "news" / "inbox").glob("*.json"):
        if requested and path.stem != requested:
            continue
        item = json.loads(path.read_text(encoding="utf-8"))
        key = item["newsId"]
        if not SLUG.fullmatch(key) or path.stem != key:
            raise ValueError("INVALID_NEWS_ID")
        if (ROOT / "news" / "state" / f"{key}.json").exists():
            continue
        published = datetime.fromisoformat(item["publishedAt"])
        if published.tzinfo is None:
            raise ValueError("UNVERIFIED_SOURCE_TIME")
        age = now - published
        if item.get("verified") is not True or not timedelta(0) <= age <= timedelta(hours=24):
            continue
        urls = [checked_url(s["url"]) for s in item["sources"]]
        if len({urlsplit(u).hostname for u in urls}) < 2:
            raise ValueError("TWO_SOURCE_LINKS_REQUIRED")
        if not item["headline"].strip() or not item["subhead"].strip() or not 3 <= len(item["paragraphs"]) <= 5:
            raise ValueError("INVALID_EDITORIAL_COPY")
        stories.append((published, key, item))
    return max(stories, default=(None, None, None))[2]


def font(size):
    path = next((p for p in FONT_PATHS if p.is_file()), None)
    if path is None:
        raise ValueError("BOLD_FONT_UNAVAILABLE")
    return ImageFont.truetype(str(path), size)


def lines_for(draw, text, face, limit):
    rows = []
    current = ""
    for word in text.split():
        candidate = (current + " " + word).strip()
        if current and draw.textlength(candidate, font=face) > limit:
            rows.append(current)
            current = word
        else:
            current = candidate
    return rows + [current]


def draw_text(draw, text, y, size, max_lines, color):
    for point_size in range(size, 29, -2):
        face = font(point_size)
        rows = lines_for(draw, text, face, 940)
        if len(rows) <= max_lines and all(draw.textlength(row, font=face) <= 940 for row in rows):
            break
    else:
        raise ValueError("HEADLINE_DOES_NOT_FIT")
    for index, row in enumerate(rows):
        draw.text((62, y + index * (point_size + 12)), row, font=face,
                  fill=color if index == 0 else "#fffaf5", stroke_width=1, stroke_fill="#161018")
    return y + len(rows) * (point_size + 12)


def photo_background(item):
    reference = item.get("photo")
    if not reference:
        if item.get("illustration") != "weather":
            raise ValueError("NO_VERIFIED_VISUAL")
        return None
    if reference.get("rightsVerified") is not True or not reference.get("credit"):
        raise ValueError("PHOTO_RIGHTS_UNVERIFIED")
    checked_url(reference["source"])
    filename = reference["file"]
    if not re.fullmatch(r"[a-z0-9-]+\.(?:jpg|png)", filename):
        raise ValueError("INVALID_PHOTO_FILE")
    with Image.open(ROOT / "news" / "photos" / filename) as picture:
        picture.load()
        return ImageOps.contain(ImageOps.exif_transpose(picture).convert("RGB"), (1080, 720))


def render(item):
    graphic = Image.new("RGB", (1080, 1350))
    d = ImageDraw.Draw(graphic)
    for y in range(1350):
        t = y / 1349
        d.line((0, y, 1080, y), fill=(round(112 * (1 - t) + 8), round(13 * (1 - t)), round(25 * (1 - t) + 6)))
    photo = photo_background(item)
    if photo is not None:
        graphic.paste(photo, ((1080 - photo.width) // 2, (720 - photo.height) // 2))
    else:
        for bounds in [(225, 330, 540, 562), (383, 248, 676, 572), (580, 337, 865, 562)]:
            d.ellipse(bounds, fill="#232c43")
        for x in range(320, 795, 90):
            d.line((x, 585, x - 38, 670), fill="#54baff", width=13)
        d.text((65, 690), "TEMSİLİ İLLÜSTRASYON", font=font(25), fill="#e5efff")
    d.polygon([(38, 62), (481, 49), (462, 71), (507, 93), (476, 110), (489, 151),
               (51, 160), (72, 139), (22, 127), (48, 102)], fill="#d11731")
    d.text((55, 78), "HABERLER KKTC", font=font(42), fill="#ffffff")
    d.polygon([(36, 776), (1025, 758), (1055, 788), (991, 821), (24, 834), (88, 806)], fill="#b81121")
    d.polygon([(31, 1136), (1015, 1124), (1050, 1160), (973, 1205), (31, 1225),
               (63, 1186), (15, 1171)], fill="#0645bd")
    headline = item["headline"].translate(str.maketrans({"i": "İ", "ı": "I"})).upper()
    bottom = draw_text(d, headline, 825, 84, 3, "#ffe54b")
    if bottom > 1131:
        raise ValueError("HEADLINE_OVERLAPS_SUBHEAD")
    draw_text(d, item["subhead"], 1151, 58, 1, "#ebf8ff")
    if photo is not None:
        draw_text(d, item["photo"]["credit"], 1250, 27 + 4, 1, "#f7e2df")
    stream = io.BytesIO()
    graphic.save(stream, "JPEG", quality=91, optimize=True)
    output = stream.getvalue()
    verify_jpeg(output)
    return output


def upload(data, key):
    token = os.environ.get("MEDIA_API_TOKEN")
    if not token:
        raise ValueError("MEDIA_API_TOKEN_MISSING")
    opener = build_opener(DirectOnly)
    request = Request(UPLOAD, method="POST", data=data, headers={
        "Authorization": "Bearer " + token,
        "Idempotency-Key": "news:" + key,
        "Content-Type": "image/jpeg",
    })
    with opener.open(request, timeout=30) as reply:
        status = reply.status
        payload = json.loads(reply.read(16000))
    verify_blob_url(payload["url"], payload["mediaId"])
    if payload.get("metadataClean") is not True:
        raise ValueError("UPLOADED_METADATA_UNVERIFIED")
    with opener.open(payload["url"], timeout=20) as reply:
        if reply.headers.get_content_type() != "image/jpeg":
            raise ValueError("BLOB_CONTENT_TYPE_INVALID")
        returned = reply.read(4_000_001)
    if len(returned) > 4_000_000:
        raise ValueError("BLOB_TOO_LARGE")
    verify_jpeg(returned)
    return {"http": status, "mediaId": payload["mediaId"], "url": payload["url"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--news-id")
    parser.add_argument("--output", type=Path, default=Path("news-handoff"))
    parser.add_argument("--upload", action="store_true")
    args = parser.parse_args()
    if args.news_id and not SLUG.fullmatch(args.news_id):
        raise ValueError("INVALID_NEWS_ID")
    item = load_news(datetime.now(CYPRUS), args.news_id)
    if not item:
        print("NO_ELIGIBLE_REVIEWED_NEWS")
        return
    image = render(item)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "news.jpg").write_bytes(image)
    handoff = {
        "newsId": item["newsId"],
        "idempotencyKey": "news:" + item["newsId"],
        "headline": item["headline"],
        "paragraphs": item["paragraphs"],
        "sources": item["sources"],
        "publishedAt": item["publishedAt"],
        "visual": "verified_photo" if item.get("photo") else "labeled_illustration",
        "metricool": {"brandId": "7549135", "provider": "facebook", "draft": True, "autoPublish": False},
    }
    if args.upload:
        handoff["blob"] = upload(image, item["newsId"])
    (args.output / "handoff.json").write_text(json.dumps(handoff, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"newsId": handoff["newsId"], "blob": handoff.get("blob")}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        code = str(error)
        print(code if re.fullmatch(r"[A-Z0-9_]+", code) else type(error).__name__, file=sys.stderr)
        sys.exit(1)
