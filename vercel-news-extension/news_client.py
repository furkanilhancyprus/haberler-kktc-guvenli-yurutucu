"""Direct HTTPS bridge for an authorized ChatGPT/Codex execution environment."""
import argparse
import json
import os
import re
import sys
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

from media_service.images import MAX_INPUT, verify_jpeg
from media_service.providers import Failure, NoRedirect, config, parse_json, retry

PRODUCTION = "https://haberler-kktc.vercel.app"
HOST = r"https://haberler-kktc-[a-z0-9-]+-ada-technology\.vercel\.app"
BLOB = r"https://fva2uclbr7ema1sw\.public\.blob\.vercel-storage\.com/haberler-kktc-news/v1/assets/[0-9a-f]{64}\.jpg"


class Client:
    def __init__(self):
        self.origin = os.environ.get("NEWS_SERVICE_ORIGIN", PRODUCTION)
        share = os.environ.get("NEWS_PREVIEW_SHARE")
        if self.origin != PRODUCTION and not re.fullmatch(HOST, self.origin):
            raise Failure("UNTRUSTED_NEWS_ORIGIN", 400)
        if share and self.origin == PRODUCTION:
            raise Failure("PREVIEW_SHARE_REQUIRES_PREVIEW", 400)
        self.opener = build_opener(NoRedirect(), HTTPCookieProcessor(CookieJar()))
        if share:
            url = self.origin + "/?" + urlencode({"_vercel_share": share})
            try:
                with self.opener.open(url, timeout=20):
                    pass
            except HTTPError as error:
                with error:
                    destination = urlsplit(error.headers.get("Location", ""))
                    if error.code not in (302, 303, 307, 308) or destination.netloc not in ("", urlsplit(self.origin).netloc):
                        raise Failure("PREVIEW_AUTHENTICATION_FAILED", error.code) from None

    def request(self, route, *, payload=None, data=None, mime=None, key=None, authenticated=False, absolute=False):
        url = route if absolute else self.origin + route
        headers = {}
        if authenticated:
            name = "MEDIA_API_TOKEN" if route == "/api/media/upload" else "NEWS_API_TOKEN"
            headers["Authorization"] = "Bearer " + (os.environ.get(name) or config("MEDIA_API_TOKEN"))
        if key:
            headers["Idempotency-Key"] = key
        if payload is not None:
            data = json.dumps(payload).encode()
            mime = "application/json"
        if mime:
            headers["Content-Type"] = mime
        req = Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
        try:
            opener = build_opener(NoRedirect()) if absolute else self.opener
            with opener.open(req, timeout=40) as response:
                limit = MAX_INPUT if absolute else 8_000_000
                raw = response.read(limit + 1)
                if response.status not in (200, 201) or not 0 < len(raw) <= limit:
                    raise Failure("INVALID_NEWS_HTTP_RESPONSE")
                return raw, response.headers.get_content_type()
        except HTTPError as error:
            with error:
                raise Failure(f"NEWS_HTTP_{error.code}", error.code, error.code in (408, 429, 500, 502, 503, 504)) from None
        except (OSError, URLError, TimeoutError):
            raise Failure("NEWS_CONNECTION_FAILED", transient=True) from None

    def publish(self, story, image=None):
        news_id = story.get("external_id")
        if not isinstance(news_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{7,99}", news_id):
            raise Failure("INVALID_NEWS_ID", 400)
        key = "news:" + news_id
        if image:
            with image.open("rb") as file:
                data = file.read(MAX_INPUT + 1)
            if len(data) > MAX_INPUT:
                raise Failure("INVALID_IMAGE_SIZE", 400)
            if data.startswith(b"\xff\xd8\xff"):
                mime = "image/jpeg"
            elif data.startswith(b"\x89PNG\r\n\x1a\n"):
                mime = "image/png"
            else:
                raise Failure("INVALID_IMAGE_FORMAT", 400)
            upload, _ = retry(lambda: self.request("/api/media/upload", data=data, mime=mime, key=key, authenticated=True))
            media = parse_json(upload, "MEDIA_UPLOAD")
            if media.get("metadataClean") is not True or media.get("status") != "uploaded":
                raise Failure("MEDIA_UPLOAD_UNVERIFIED")
            story = {**story, "media_url": media["url"]}
        raw, _ = retry(lambda: self.request("/api/news/publish", payload=story, key=key, authenticated=True))
        outcome = parse_json(raw, "NEWS_PUBLISH")
        path = "/haber/" + news_id
        if outcome.get("news_url") != self.origin + path or outcome.get("status") != "published":
            raise Failure("NEWS_PUBLISH_UNVERIFIED")
        html, mime = retry(lambda: self.request(path))
        if mime != "text/html" or outcome["media_url"].encode() not in html:
            raise Failure("NEWS_PAGE_UNVERIFIED")
        permanent = outcome["media_url"]
        if not re.fullmatch(BLOB, permanent):
            raise Failure("INVALID_NEWS_MEDIA")
        jpeg, mime = retry(lambda: self.request(permanent, absolute=True))
        if mime != "image/jpeg":
            raise Failure("NEWS_IMAGE_UNVERIFIED")
        verify_jpeg(jpeg)
        return {**outcome, "page_verified": True, "media_verified": True, "brand_id": "7549135"}

    def state(self, payload):
        raw, _ = retry(lambda: self.request("/api/news/metricool", payload=payload, authenticated=True))
        return parse_json(raw, "NEWS_DELIVERY")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["publish", "state"])
    parser.add_argument("json_file", type=Path)
    parser.add_argument("--image", type=Path)
    args = parser.parse_args()
    value = json.loads(args.json_file.read_text(encoding="utf-8-sig"))
    client = Client()
    out = client.publish(value, args.image) if args.action == "publish" else client.state(value)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Failure as error:
        print(json.dumps({"success": False, "error": error.code}), file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, KeyError, TypeError):
        print('{"success":false,"error":"INVALID_LOCAL_INPUT_OR_RESPONSE"}', file=sys.stderr)
        sys.exit(1)
