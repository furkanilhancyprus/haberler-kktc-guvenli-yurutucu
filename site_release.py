"""Prepare a single news release from the current Vercel deployment's sources."""

import argparse
import base64
import hashlib
import html
import json
import os
import re
from datetime import datetime
from pathlib import Path
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from verify_media import MAX_BYTES, UPLOAD, DirectOnly, verify_blob_url, verify_jpeg


SITE = "https://haberler-kktc.vercel.app"
ARCHIVE = "public/son-haberler/index.html"
HOME = "public/index.html"
CATEGORIES = dict(gundem="Gündem", dunya="Dünya", siyaset="Siyaset", spor="Spor",
                  ekonomi="Ekonomi", teknoloji="Teknoloji", yasam="Yaşam", magazin="Magazin")
CARD = re.compile(r'<article class="story-card">.*?</article>', re.S)
LATEST = re.compile(r'<a class="latest-item"[^>]*>.*?</a>', re.S)


def sha(raw):
    return hashlib.sha1(raw).hexdigest()


def http(url, limit, mime):
    req = Request(url, headers={"User-Agent": "HaberlerKKTC-Release/1"})
    with build_opener(DirectOnly()).open(req, timeout=25) as response:
        if response.status != 200 or response.headers.get_content_type() != mime:
            raise ValueError("UNEXPECTED_PUBLIC_RESPONSE")
        data = response.read(limit + 1)
    if not 0 < len(data) <= limit:
        raise ValueError("INVALID_DOWNLOAD_SIZE")
    return data


def uploaded_image(receipt):
    if receipt.get("metadataClean") is not True or receipt.get("status") != "uploaded":
        raise ValueError("UPLOAD_UNVERIFIED")
    verify_blob_url(receipt["url"], receipt["mediaId"])
    return http(receipt["url"], MAX_BYTES, "image/jpeg")


def stage_image(news_id, data):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{7,99}", news_id):
        raise ValueError("INVALID_NEWS_ID")
    mime = "image/jpeg" if data.startswith(b"\xff\xd8\xff") else "image/png"
    if not 0 < len(data) <= MAX_BYTES or (mime == "image/png" and not data.startswith(b"\x89PNG\r\n\x1a\n")):
        raise ValueError("INVALID_IMAGE_INPUT")
    token = os.environ.get("MEDIA_API_TOKEN", "")
    if not token:
        raise ValueError("MEDIA_API_TOKEN_MISSING")
    request = Request(UPLOAD, method="POST", data=data, headers={"Content-Type": mime,
                      "Authorization": "Bearer " + token, "Idempotency-Key": "news:" + news_id})
    opener = build_opener(DirectOnly())
    for attempt in range(3):
        try:
            with opener.open(request, timeout=30) as reply:
                return uploaded_image(json.loads(reply.read(64_001)))
        except HTTPError as error:
            with error:
                if error.code not in (408, 429, 500, 502, 503, 504) or attempt == 2:
                    raise ValueError(f"MEDIA_HTTP_{error.code}") from None
        except (URLError, TimeoutError):
            if attempt == 2:
                raise ValueError("MEDIA_CONNECTION_FAILED") from None
        sleep(2 ** attempt)


def verified_handoff(package, expected):
    news_id = package["newsId"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{7,99}", news_id):
        raise ValueError("INVALID_NEWS_ID")
    if package["category"] not in CATEGORIES:
        raise ValueError("INVALID_CATEGORY")
    paths = {HOME: "/", ARCHIVE: "/son-haberler/",
             f"public/kategori/{package['category']}/index.html": f"/kategori/{package['category']}/",
             f"public/haber-{news_id}.html": f"/haber-{news_id}.html",
             f"public/assets/news-{news_id}.jpg": f"/assets/news-{news_id}.jpg"}
    if paths.keys() != expected.keys():
        raise ValueError("INVALID_RELEASE_RECEIPT")
    for path, route in paths.items():
        jpeg = path.endswith(".jpg")
        data = http(SITE + route, MAX_BYTES, "image/jpeg" if jpeg else "text/html")
        if sha(data) != expected[path]:
            raise ValueError("PUBLIC_RELEASE_UNVERIFIED: " + route)
        if jpeg:
            verify_jpeg(data)
    post = package["socialText"].strip()
    publish_at = datetime.fromisoformat(package["scheduleAt"])
    if not 1 <= len(post) <= 15000 or publish_at.utcoffset() is None:
        raise ValueError("INVALID_METRICOOL_HANDOFF")
    if publish_at <= datetime.now(publish_at.tzinfo):
        raise ValueError("POST_TIME_IN_PAST")
    return {"newsId": news_id, "idempotencyKey": "news:" + news_id, "status": "site_verified",
            "siteUrl": SITE + f"/haber-{news_id}.html", "mediaUrl": SITE + f"/assets/news-{news_id}.jpg",
            "brandId": "7549135", "provider": "facebook", "draft": True, "autoPublish": False,
            "text": post, "publicationDate": publish_at.isoformat(timespec="seconds"),
            "timezone": "Europe/Bucharest"}


def https_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("INVALID_SOURCE_URL")
    return value


def merge_cards(page, pattern, entry, limit=None):
    matches = list(pattern.finditer(page))
    if not matches:
        raise ValueError("UNRECOGNIZED_LIST_TEMPLATE")
    first, last = matches[0], matches[-1]
    old = [m[0] for m in matches]

    def date(markup):
        value = re.search(r'datetime="([^"]+)"', markup)
        return datetime.fromisoformat(value[1]).timestamp() if value else 0

    ordered = sorted([entry, *old], key=date, reverse=True)[:limit]
    # Only replace the list when its surrounding markup is unambiguous.
    for a, b in zip(matches, matches[1:]):
        if page[a.end():b.start()].strip():
            raise ValueError("NONCONTIGUOUS_LIST_TEMPLATE")
    return page[:first.start()] + "".join(ordered) + page[last.end():]


def replace_once(page, pattern, value):
    changed, count = re.subn(pattern, lambda _: value, page, count=1, flags=re.S)
    if not count:
        raise ValueError("UNRECOGNIZED_ARTICLE_TEMPLATE")
    return changed


def build(snapshot, package, read_source, image, template):
    news_id = package["newsId"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{7,99}", news_id) or package.get("verified") is not True:
        raise ValueError("UNVERIFIED_NEWS")
    title = package["headline"].strip()
    paragraphs = package["paragraphs"]
    sources = package["sourceUrls"]
    tags = package["tags"]
    if (not title or not paragraphs or not sources
            or not all(isinstance(x, list) for x in (paragraphs, sources, tags))
            or not all(isinstance(x, str) and x.strip() for x in [*paragraphs, *sources, *tags])):
        raise ValueError("INCOMPLETE_NEWS")
    sources = [https_url(url) for url in sources]
    category = package["category"]
    label = CATEGORIES[category]
    local = datetime.fromisoformat(package["publishedAt"])
    if local.utcoffset() is None:
        raise ValueError("NEWS_TIMEZONE_REQUIRED")
    iso = local.isoformat(timespec="seconds")
    when = f'<time datetime="{iso}">{local:%d.%m.%Y · %H:%M}</time>'
    escaped = html.escape(title)
    href = f"/haber-{news_id}.html"
    photo = f"/assets/news-{news_id}.jpg"
    category_path = f"public/kategori/{category}/index.html"
    files = {row["path"].removeprefix("src/"): row for row in snapshot
             if row["path"].startswith("src/")}
    if not {HOME, ARCHIVE, category_path, "vercel.json", template} <= files.keys():
        raise ValueError("INCOMPLETE_DEPLOYMENT_SNAPSHOT")
    if "public" + href in files or "public" + photo in files:
        raise ValueError("NEWS_ALREADY_PRESENT")

    def current(path):
        content = read_source(path)
        if sha(content) != files[path]["uid"]:
            raise ValueError("DEPLOYMENT_SOURCE_CHANGED: " + path)
        return content.decode("utf-8")

    archive = current(ARCHIVE)
    source_ids = {hashlib.sha256(url.encode()).hexdigest() for url in sources}
    if (href in archive or f'<h3>{escaped}</h3>' in archive
            or any(source in archive for source in source_ids)):
        raise ValueError("NEWS_ALREADY_PRESENT")
    verify_jpeg(image)
    page = current(template)
    body = "".join("<p>" + html.escape(p).replace("\n", "<br>") + "</p>" for p in paragraphs)
    links = " · ".join(f'<a href="{html.escape(url)}" rel="noopener noreferrer">{html.escape(url)}</a>'
                       for url in sources)
    breadcrumbs = f'<a href="/">Ana sayfa</a> / <a href="/kategori/{category}">{label}</a>'
    article = (f'<nav class="breadcrumbs" aria-label="Sayfa yolu">{breadcrumbs}</nav>'
               f'<article><header class="article-header"><span class="kicker">{label}</span>'
               f'<h1>{escaped}</h1><div class="article-meta"><span>Haberler KKTC</span>{when}</div></header>'
               f'<figure class="article-photo"><img src="{photo}" alt="{escaped}" fetchpriority="high"></figure>'
               f'<div class="article-columns"><div class="article-copy"><div class="article-text">{body}</div>'
               f'<p class="source">Kaynak: {links}</p><p>{html.escape(" · ".join(tags))}</p></div></div></article>')
    page = replace_once(page, r'<title>.*?</title>', f'<title>{escaped} | Haberler KKTC</title>')
    page = replace_once(page, r'(<main\b[^>]*>).*?</main>',
                        re.search(r'<main\b[^>]*>', page)[0] + article + '</main>')
    fingerprints = " ".join(sorted(source_ids))
    card = (f'<article class="story-card"><a href="{href}" data-source="{fingerprints}"><div class="card-photo">'
            f'<img src="{photo}" alt="{escaped}" loading="lazy" decoding="async"></div>'
            f'<div class="card-body"><span class="kicker">{label}</span><h3>{escaped}</h3>{when}</div></a></article>')
    side = (f'<a class="latest-item" href="{href}"><time datetime="{iso}">{local:%H:%M}</time>'
            f'<span><small>{label}</small><strong>{escaped}</strong></span>'
            f'<img class="latest-photo" src="{photo}" alt="" width="52" height="60" loading="lazy"></a>')
    home = current(HOME)
    home = merge_cards(home, LATEST, side, limit=len(LATEST.findall(home)))

    def desk(match):
        section = match[0]
        if f'<h2>{label}</h2>' not in section or not CARD.search(section):
            return section
        return merge_cards(section, CARD, card, limit=len(CARD.findall(section)))

    home = re.sub(r'<section class="desk">.*?</section>', desk, home, flags=re.S)
    updates = {"public" + href: page.encode(), "public" + photo: image, HOME: home.encode(),
               ARCHIVE: merge_cards(archive, CARD, card).encode(),
               category_path: merge_cards(current(category_path), CARD, card).encode()}
    manifest = []
    for path, row in files.items():
        if path not in updates:
            ref = {"file": path, "sha": row["uid"]}
            if isinstance(row.get("size"), int):
                ref["size"] = row["size"]
            manifest.append(ref)
    manifest.extend({"file": path, "data": base64.b64encode(raw).decode(), "encoding": "base64"}
                    for path, raw in updates.items())
    return manifest, {path: sha(raw) for path, raw in updates.items()}


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--snapshot", type=Path)
    cli.add_argument("--package", type=Path, required=True)
    cli.add_argument("--sources", type=Path)
    cli.add_argument("--image", type=Path)
    cli.add_argument("--blob-receipt", type=Path)
    cli.add_argument("--upload-image", action="store_true", help="Stage --image using the authorized media API")
    cli.add_argument("--template")
    cli.add_argument("--output", type=Path, required=True)
    cli.add_argument("--verify-production", action="store_true")
    args = cli.parse_args()
    package = json.loads(args.package.read_text(encoding="utf-8-sig"))
    if args.verify_production:
        handoff = args.output / "metricool-handoff.json"
        handoff.unlink(missing_ok=True)
        expected = json.loads((args.output / "verify-sha1.json").read_text(encoding="ascii"))
        receipt = verified_handoff(package, expected)
        handoff.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        return
    if not all((args.snapshot, args.sources, args.template)) or bool(args.image) == bool(args.blob_receipt):
        cli.error("building requires --snapshot, --sources, --template and one image input")
    if args.upload_image and not args.image:
        cli.error("--upload-image requires --image")
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8-sig"))
    if args.blob_receipt:
        receipt = json.loads(args.blob_receipt.read_text(encoding="utf-8-sig"))
        image = uploaded_image(receipt)
    else:
        if not 0 < args.image.stat().st_size <= MAX_BYTES:
            raise ValueError("INVALID_IMAGE_SIZE")
        with args.image.open("rb") as file:
            image = file.read(MAX_BYTES + 1)
    if len(image) > MAX_BYTES:
        raise ValueError("INVALID_IMAGE_SIZE")
    if args.upload_image:
        if package.get("verified") is not True:
            raise ValueError("UNVERIFIED_NEWS")
        image = stage_image(package["newsId"], image)
    deployment, expected = build(snapshot, package, lambda path: (args.sources / path).read_bytes(),
                                 image, args.template)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in (("deployment-files", deployment), ("verify-sha1", expected)):
        (args.output / (name + ".json")).write_text(json.dumps(value, separators=(",", ":")), encoding="ascii")


if __name__ == "__main__":
    main()
