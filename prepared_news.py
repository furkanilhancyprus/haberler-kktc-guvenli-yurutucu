"""Validate a ChatGPT news package and hand its supplied JPEG to Metricool."""
import argparse
import base64
import hashlib
import io
import json
import os
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener
from zoneinfo import ZoneInfo

from PIL import Image, ImageChops, ImageStat

from verify_media import DirectOnly, MAX_BYTES, UPLOAD, verify_blob_url, verify_jpeg

ZONE = "Asia/Famagusta"
CYPRUS = ZoneInfo(ZONE)
BRAND = "7549135"
POSTS = "/v2/scheduler/posts"
API = "https://app.metricool.com/api"
REPO = "furkanilhancyprus/haberler-kktc-guvenli-yurutucu"
INBOX = Path("news/inbox")
SIZE = (1080, 1350)
ELECTION_PROBE = "kktc-secim-227642-secmen-998-sandik-20261116"
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{7,88}")
OPENER = build_opener(DirectOnly)
TRANSIENT = {408, 429, 500, 502, 503, 504}


class TransferError(Exception):
    pass


def fetch(url, *, label, headers=None, body=None, method="GET", limit=1_000_000, attempts=3):
    for attempt in range(attempts):
        try:
            request = Request(url, data=body, headers=headers or {}, method=method)
            with OPENER.open(request, timeout=25) as response:
                data = response.read(limit + 1)
            if len(data) > limit:
                raise TransferError(label + "_RESPONSE_TOO_LARGE")
            return data
        except HTTPError as error:
            code = error.code
            error.close()
            if code not in TRANSIENT or attempt + 1 == attempts:
                raise TransferError(f"{label}_HTTP_{code}") from None
        except (OSError, URLError):
            if attempt + 1 == attempts:
                raise TransferError(label + "_NETWORK_ERROR") from None
        time.sleep(2 ** attempt)


def encode(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def source_host(value):
    url = urlsplit(value)
    if (url.scheme != "https" or not url.hostname or "." not in url.hostname
            or url.username or url.password or url.port not in (None, 443)
            or not url.path.strip("/") or any(char.isspace() for char in value)):
        raise TransferError("INVALID_SOURCE_URL")
    return url.hostname.removeprefix("www.")


def remove_metadata(raw):
    with Image.open(io.BytesIO(raw), formats=["JPEG", "PNG"]) as image:
        if (image.size != SIZE and image.format != "PNG") or image.getexif().get(274, 1) != 1:
            raise TransferError("INVALID_JPEG_SIZE_OR_ORIENTATION")
        # A new RGB image carries pixels only, including when the input has EXIF/XMP/ICC.
        clean = Image.new("RGB", SIZE)
        clean.paste(image.convert("RGB").resize(SIZE, Image.Resampling.LANCZOS))
    stream = io.BytesIO()
    clean.save(stream, "JPEG", quality=94, optimize=True)
    data = stream.getvalue()
    if len(data) > MAX_BYTES:
        raise TransferError("CLEAN_JPEG_TOO_LARGE")
    verify_jpeg(data)
    return data


def load_package(path, now, *, recovering=False, allow_probe=False):
    if path.stat().st_size > 900_000:
        raise TransferError("PACKAGE_TOO_LARGE")
    packet = json.loads(path.read_text(encoding="utf-8"))
    news_id = packet["newsId"]
    if not SLUG.fullmatch(news_id) or path.parent.name != news_id:
        raise TransferError("INVALID_NEWS_ID")
    probe = allow_probe and news_id == ELECTION_PROBE and packet["status"] == "test_ready"
    if probe:
        if (packet.get("draft") is not True or packet.get("autoPublish") is not False
                or packet.get("visualType") != "AI_GENERATED_TEST_ILLUSTRATION"
                or packet.get("illustrationDisclosureRequired") is not True
                or packet.get("verification") != "confirmed_public_sources"):
            raise TransferError("INVALID_TECHNICAL_PROBE")
    elif (packet["status"] != "ready" or packet.get("verified") is not True
            or packet.get("imageRightsVerified") is not True):
        raise TransferError("MISSING_EDITORIAL_VERIFICATION")
    if (packet["timezone"] != ZONE or not packet["headline"].strip()
            or packet["imagePath"] not in {"image.jpg", "image.png", str(path.parent / "image.jpg"), str(path.parent / "image.png")}):
        raise TransferError("MISSING_EDITORIAL_VERIFICATION")
    urls = packet["sourceUrls"]
    if not isinstance(urls, list) or not 2 <= len(urls) <= 10 or len({source_host(url) for url in urls}) < 2:
        raise TransferError("TWO_DISTINCT_SOURCE_HOSTS_REQUIRED")
    published = datetime.fromisoformat(packet["publishedAt"])
    requested = ((now + timedelta(minutes=30)).astimezone(CYPRUS) if probe
                 else datetime.fromisoformat(packet["publicationDate"]))
    if (published.utcoffset() is None or requested.utcoffset() is None
            or (not (probe or recovering) and not timedelta(0) <= now - published <= timedelta(hours=24))
            or (not recovering and not now + timedelta(minutes=3) <= requested <= now + timedelta(hours=48))
            or requested.utcoffset() != requested.astimezone(CYPRUS).utcoffset()
            or requested.astimezone(CYPRUS).replace(fold=0).utcoffset()
                != requested.astimezone(CYPRUS).replace(fold=1).utcoffset()):
        raise TransferError("INVALID_OR_EXPIRED_TIMES")
    if "imageBase64" in packet:
        raw = base64.b64decode(packet["imageBase64"], validate=True)
        caption = packet["postText"].strip()
    else:
        image_path = path.with_name("image.png" if packet["imagePath"].endswith(".png") else "image.jpg")
        post_path = path.with_name("post.txt")
        if packet["postPath"] not in {"post.txt", str(post_path)}:
            raise TransferError("INVALID_POST_PATH")
        if image_path.stat().st_size > MAX_BYTES or post_path.stat().st_size > 60_000:
            raise TransferError("PACKAGE_TOO_LARGE")
        raw = image_path.read_bytes()
        caption = post_path.read_text(encoding="utf-8").strip()
    if not caption or len(caption) > 15_000:
        raise TransferError("INVALID_POST_TEXT")
    if probe:
        caption = "[TEKNİK TEST • YAYIMLANMAYACAK • YAPAY ZEKÂ İLLÜSTRASYONU]\n\n" + caption
        packet.setdefault("imageSha256", hashlib.sha256(raw).hexdigest())
    if hashlib.sha256(raw).hexdigest() != packet["imageSha256"]:
        raise TransferError("JPEG_HASH_MISMATCH")
    return packet, caption, requested, remove_metadata(raw)


def github_state(news_id, value=None, previous=None):
    token = os.environ["GITHUB_TOKEN"]
    url = f"https://api.github.com/repos/{REPO}/contents/news/state/{news_id}.json"
    headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"}
    if value is None:
        try:
            item = json.loads(fetch(url + "?ref=main", label="STATE_READ", headers=headers))
            return json.loads(base64.b64decode(item["content"])), item["sha"]
        except TransferError as error:
            if str(error) != "STATE_READ_HTTP_404":
                raise
            return None, None
    payload = {
        "branch": "main",
        "message": f"Record Metricool delivery state for {news_id}",
        "content": base64.b64encode(encode(value) + b"\n").decode("ascii"),
    }
    if previous:
        payload["sha"] = previous
    receipt = fetch(url, label="STATE_WRITE", headers=headers, body=encode(payload), method="PUT", attempts=1)
    return json.loads(receipt)["content"]["sha"]


def metricool(path, token, user_id, query=None, data=None):
    params = {"blogId": BRAND, "userId": user_id, **(query or {})}
    return fetch(API + path + "?" + urlencode(params), label="METRICOOL",
                 headers={"X-Mc-Auth": token, "Content-Type": "application/json"},
                 body=encode(data) if data is not None else None,
                 method="POST" if data is not None else "GET", attempts=1 if data is not None else 3)


def metricool_jpeg(url, expected):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "static.metricool.com" or not parsed.path.startswith("/planner/"):
        raise TransferError("INDEPENDENT_METRICOOL_MEDIA_REQUIRED")
    data = fetch(url, label="METRICOOL_COPY", limit=MAX_BYTES)
    with Image.open(io.BytesIO(data), formats=["JPEG"]) as image:
        if image.size != SIZE:
            raise TransferError("METRICOOL_COPY_SIZE_MISMATCH")
        actual = image.convert("RGB").resize((96, 120), Image.Resampling.LANCZOS)
    with Image.open(io.BytesIO(expected)) as original:
        reference = original.resize((96, 120), Image.Resampling.LANCZOS)
    if max(ImageStat.Stat(ImageChops.difference(actual, reference)).mean) > 5:
        raise TransferError("METRICOOL_COPY_CONTENT_MISMATCH")


def normalized_media(clean, news_id, token, user_id, media_token):
    blob = json.loads(fetch(UPLOAD, label="BLOB_UPLOAD", method="POST", body=clean, limit=16_000,
                            headers={"Authorization": "Bearer " + media_token, "Content-Type": "image/jpeg",
                                     "Idempotency-Key": "news:" + news_id}))
    verify_blob_url(blob["url"], blob["mediaId"])
    if blob.get("metadataClean") is not True:
        raise TransferError("BLOB_METADATA_UNVERIFIED")
    reply = metricool("/actions/normalize/image/url", token, user_id, {"url": blob["url"], "folder": "PLANNER"})
    media = reply.decode("utf-8").strip()
    if not media.startswith("https://"):
        parsed = json.loads(media)
        if isinstance(parsed, dict):
            parsed = parsed.get("data", parsed)
        media = parsed.get("url") if isinstance(parsed, dict) else parsed
    if not isinstance(media, str):
        raise TransferError("METRICOOL_MEDIA_URL_MISSING")
    metricool_jpeg(media, clean)
    return media


def calendar_match(caption, requested, token, user_id):
    interval = {
        "start": local_time(requested - timedelta(days=3)),
        "end": local_time(requested + timedelta(days=3)),
        "timezone": ZONE,
    }
    reply = json.loads(metricool(POSTS, token, user_id, interval))
    if isinstance(reply, dict) and reply.get("page"):
        page = reply["page"]
        if page.get("totalPages", 1) != 1 or page.get("next"):
            raise TransferError("METRICOOL_CALENDAR_INCOMPLETE")
    rows = reply.get("data") if isinstance(reply, dict) else reply
    if not isinstance(rows, list):
        raise TransferError("METRICOOL_CALENDAR_UNREADABLE")
    matches = [row for row in rows if row.get("text", "").strip() == caption]
    if len(matches) > 1:
        raise TransferError("METRICOOL_DUPLICATE_POSTS_FOUND")
    return matches[0] if matches else None


def local_time(date):
    return date.astimezone(CYPRUS).replace(tzinfo=None).isoformat(timespec="seconds")


def post_body(caption, date, media):
    return {
        "text": caption,
        "media": [media],
        "providers": [{"network": "facebook"}],
        "facebookData": {"type": "POST"},
        "publicationDate": {"dateTime": local_time(date), "timezone": ZONE},
        "autoPublish": True,
        "draft": False,
    }


def post_id(post):
    value = post.get("id")
    if not re.fullmatch(r"[1-9][0-9]*", str(value)):
        raise TransferError("METRICOOL_POST_ID_MISSING")
    return value


def deliver(path, validate_only, state=None, sha=None, *, allow_probe=False):
    now = datetime.now(UTC)
    packet, caption, requested, clean = load_package(path, now, recovering=state is not None, allow_probe=allow_probe)
    news_id = packet["newsId"]
    if validate_only:
        return {"newsId": news_id, "status": "input_verified", "dimensions": list(SIZE), "metadataClean": True}
    settings = {name: os.environ.get(name) for name in ("METRICOOL_API_TOKEN", "METRICOOL_USER_ID", "MEDIA_API_TOKEN")}
    for name, value in settings.items():
        if not value:
            raise TransferError(name + "_MISSING")
    token, user_id, media_token = settings.values()
    if not user_id.isdecimal():
        raise TransferError("METRICOOL_USER_ID_INVALID")
    fingerprint = hashlib.sha256(encode([caption, packet["imageSha256"]])).hexdigest()
    if state and state["packageSha256"] != fingerprint:
        raise TransferError("CLAIMED_PACKAGE_CHANGED")
    if state:
        requested = datetime.fromisoformat(state["requestedDate"])
    post = None
    if state and state.get("metricoolPostId"):
        existing_id = post_id({"id": state["metricoolPostId"]})
    else:
        post = calendar_match(caption, requested, token, user_id)
        existing_id = post_id(post) if post else None
    if state and not existing_id:
        raise TransferError("METRICOOL_POST_UNCERTAIN_NO_RETRY")
    if not state:
        media = None if existing_id else normalized_media(clean, news_id, token, user_id, media_token)
        if not existing_id and requested < datetime.now(UTC) + timedelta(minutes=1):
            raise TransferError("PUBLICATION_TIME_EXPIRED")
        state = {"newsId": news_id, "status": "schedule_pending", "packageSha256": fingerprint,
                 "requestedDate": requested.isoformat(), "workflowRunId": os.environ.get("GITHUB_RUN_ID"),
                 "metricoolMediaUrl": media}
        if existing_id:
            state["metricoolPostId"] = existing_id
        sha = github_state(news_id, state)
        if not existing_id:
            try:
                created = json.loads(metricool(POSTS, token, user_id, data=post_body(caption, requested, media)))
                existing_id = post_id(created["data"])
            except (TransferError, ValueError, KeyError, TypeError):
                post = calendar_match(caption, requested, token, user_id)
                if post is None:
                    raise
                existing_id = post_id(post)
            state["metricoolPostId"] = existing_id
            sha = github_state(news_id, state, previous=sha)
    post = json.loads(metricool(f"{POSTS}/{existing_id}", token, user_id))["data"]
    attached = post.get("media")
    publication = post.get("publicationDate", {})
    if (str(post_id(post)) != str(existing_id) or post.get("text", "").strip() != caption
            or post.get("draft") is not False or post.get("autoPublish") is not True
            or [row.get("network") for row in post.get("providers", [])] != ["facebook"]
            or post.get("facebookData", {}).get("type") != "POST"
            or publication.get("timezone") != ZONE or publication.get("dateTime") != local_time(requested)
            or not isinstance(attached, list) or len(attached) != 1
            or (state.get("metricoolMediaUrl") and attached[0] != state["metricoolMediaUrl"])):
        raise TransferError("METRICOOL_SCHEDULE_READBACK_MISMATCH")
    if not state.get("metricoolMediaUrl"):
        # A pre-existing planner entry was never created by this package.
        raise TransferError("EXISTING_DRAFT_REQUIRES_MANUAL_MATCH")
    metricool_jpeg(attached[0], clean)
    state.update(status="scheduled_verified", publicationDate=publication, draft=False, autoPublish=True,
                 dimensions=list(SIZE), metadataClean=True,
                 metricoolPostUrl=f"https://app.metricool.com/planner/calendar?blogId={BRAND}")
    if str(post.get("uuid", "")).isascii() and re.fullmatch(r"[a-zA-Z0-9-]+", str(post.get("uuid", ""))):
        state["metricoolPostUrl"] += "&openWithPostUuid=" + str(post["uuid"])
    github_state(news_id, state, previous=sha)
    return state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--news-id")
    args = parser.parse_args()
    if args.news_id and not SLUG.fullmatch(args.news_id):
        raise TransferError("INVALID_NEWS_ID")
    paths = sorted(INBOX.glob("*/manifest.json"))
    if args.news_id:
        paths = [path for path in paths if path.parent.name == args.news_id]
        if not paths:
            raise TransferError("PACKAGE_NOT_FOUND")
    failed = False
    for path in paths:
        try:
            allow_probe = args.news_id == ELECTION_PROBE
            if path.parent.name == ELECTION_PROBE and not allow_probe:
                continue
            state, sha = None, None
            if not args.validate_only and SLUG.fullmatch(path.parent.name):
                state, sha = github_state(path.parent.name)
                if state and state.get("status") not in {"draft_pending", "schedule_pending"}:
                    print(json.dumps({"newsId": path.parent.name, "status": "already_recorded"}))
                    continue
            print(json.dumps(deliver(path, args.validate_only, state, sha, allow_probe=allow_probe), ensure_ascii=False))
        except Exception as error:
            code = str(error) if isinstance(error, (TransferError, ValueError)) else ""
            print(code if re.fullmatch(r"[A-Z0-9_]+", code) else type(error).__name__, file=sys.stderr)
            failed = True
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except TransferError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
