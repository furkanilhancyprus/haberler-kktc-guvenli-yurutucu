import hmac
import json
import os
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

from api.media import enforce_rate
from media_service import news_page
from media_service.news import CATEGORIES, News
from media_service.providers import Failure, config, parse_json

SITE = "https://haberler-kktc.vercel.app"


def origin(production):
    if production:
        return SITE
    host = os.environ.get("VERCEL_URL", "")
    if re.fullmatch(r"haberler-kktc-[a-z0-9-]+-ada-technology\.vercel\.app", host):
        return "https://" + host
    return SITE


class handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        self.handle_news()

    def do_GET(self):
        self.handle_news()

    def do_HEAD(self):
        self.handle_news()

    def handle_news(self):
        try:
            self.execute()
        except Failure as error:
            self.reply(error.status, {"success": False, "error": error.code, "retryable": error.transient})
        except (TypeError, ValueError):
            self.reply(400, {"success": False, "error": "INVALID_NEWS_REQUEST"})
        except Exception as error:
            print(json.dumps({"newsErrorType": type(error).__name__}), flush=True)
            self.reply(503, {"success": False, "error": "NEWS_SERVICE_UNAVAILABLE", "retryable": True})

    def execute(self):
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        get = lambda key: query.get(key, [None])[0]
        route = url.path.rstrip("/")
        if route == "/api/news":
            view = get("view")
        elif route.startswith("/api/news/"):
            view = route[len("/api/news/"):]
        else:
            view = get("view")
        if view in ("publish", "metricool"):
            if self.command != "POST":
                raise Failure("METHOD_NOT_ALLOWED", 405)
            token = os.environ.get("NEWS_API_TOKEN") or config("MEDIA_API_TOKEN")
            if len(token) < 32:
                raise Failure("INVALID_NEWS_SERVER_TOKEN", 503)
            if not hmac.compare_digest(("Bearer " + token).encode(), self.headers.get("Authorization", "").encode()):
                raise Failure("UNAUTHORIZED", 401)
            enforce_rate()
            if self.headers.get_content_type() != "application/json" or self.headers.get("Transfer-Encoding") or self.headers.get("Content-Encoding"):
                raise Failure("INVALID_NEWS_CONTENT_TYPE", 415)
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 110_000:
                raise Failure("INVALID_NEWS_REQUEST_SIZE", 413)
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise Failure("INCOMPLETE_NEWS_REQUEST", 400)
            try:
                data = parse_json(raw, "NEWS_REQUEST")
            except Failure:
                raise Failure("INVALID_NEWS_JSON", 400) from None
            news = News()
            if view == "publish":
                row, created = news.publish(data, self.headers.get("Idempotency-Key"))
                self.reply(201 if created else 200, {"success": True, "created": created,
                           "news_id": row["external_id"], "status": "published", "media_url": row["media_url"],
                           "news_url": origin(news.production) + "/haber/" + row["external_id"]})
            else:
                news_id = data.get("external_id")
                self.reply(200, {"success": True, **news.metricool(news_id, data if data.get("operation") else None)})
            return

        if self.command not in ("GET", "HEAD"):
            raise Failure("METHOD_NOT_ALLOWED", 405)
        if view not in ("article", "home", "archive", "category"):
            raise Failure("NEWS_ROUTE_NOT_FOUND", 404)
        news = News()
        if view == "article":
            page = news_page.article(news.article(get("external_id")), origin(news.production), news.production)
        else:
            category = get("category") if view == "category" else None
            if view == "category" and category not in CATEGORIES:
                raise Failure("NEWS_CATEGORY_NOT_FOUND", 404)
            try:
                rows = news.list(category)
            except Failure:
                rows = []
            page = news_page.listing(rows, category, view == "home")
        self.reply(200, page, "text/html; charset=utf-8")

    def reply(self, status, payload, content_type="application/json; charset=utf-8"):
        data = (payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if status == 429:
            self.send_header("Retry-After", "60")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)
