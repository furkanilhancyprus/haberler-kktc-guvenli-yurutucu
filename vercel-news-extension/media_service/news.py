import hashlib
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, build_opener

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .images import verify_jpeg
from .providers import Failure, NoRedirect, config, image_available, parse_json, retry
from .service import encode, now
from .store import Store

ID = re.compile(r"[a-z0-9][a-z0-9-]{7,99}")
BLOB_HOST = "fva2uclbr7ema1sw.public.blob.vercel-storage.com"
BLOB_ORIGIN = f"https://{BLOB_HOST}/"
MEDIA = re.compile(r"haberler-kktc-temp/v1/images/[0-9a-f]{40}\.jpg|haberler-kktc-news/v1/assets/[0-9a-f]{64}\.jpg")
CATEGORIES = {"gundem": "Gündem", "dunya": "Dünya", "siyaset": "Siyaset", "spor": "Spor",
              "ekonomi": "Ekonomi", "teknoloji": "Teknoloji", "yasam": "Yaşam", "magazin": "Magazin"}


def digest(value):
    return hashlib.sha256(value).hexdigest()


def checked_text(value, length):
    if not isinstance(value, str) or not 0 < len(value.strip()) <= length or "\x00" in value:
        raise Failure("INVALID_NEWS_FIELDS", 400)
    return value.strip()


def valid_id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise Failure("INVALID_NEWS_ID", 400)
    return value


def source_url(value):
    value = checked_text(value, 2000)
    try:
        url = urlsplit(value)
        if (url.scheme == "https" and url.hostname and not url.username and not url.password
                and url.port in (None, 443) and not any(c.isspace() for c in value)):
            return urlunsplit(("https", url.hostname, url.path or "/", url.query, ""))
    except ValueError:
        pass
    raise Failure("INVALID_NEWS_SOURCE", 400)


def media_url(value):
    if not isinstance(value, str) or not value.startswith(BLOB_ORIGIN) or not MEDIA.fullmatch(value[len(BLOB_ORIGIN):]):
        raise Failure("INVALID_NEWS_MEDIA", 400)
    return value


def validate(data):
    if data.get("status") != "published":
        raise Failure("INVALID_NEWS_STATUS", 400)
    category = checked_text(data.get("category"), 35)
    labels = {label.casefold(): slug for slug, label in CATEGORIES.items()}
    category = labels.get(category.casefold(), category)
    if category not in CATEGORIES:
        raise Failure("INVALID_NEWS_CATEGORY", 400)
    tags = data.get("tags", [])
    if not isinstance(tags, list) or len(tags) > 12:
        raise Failure("INVALID_NEWS_TAGS", 400)
    return {"external_id": valid_id(data.get("external_id")), "title": checked_text(data.get("title"), 200),
            "content": checked_text(data.get("content"), 18000), "summary": checked_text(data.get("summary"), 320),
            "category": category, "source_name": checked_text(data.get("source_name"), 120),
            "source_url": source_url(data.get("source_url")), "tags": [checked_text(t, 55) for t in tags],
            "media_url": media_url(data.get("media_url"))}


class NewsStore(Store):
    def put(self, path, data, mime, etag=None):
        if not etag:
            return super().put(path, data, mime)
        # vercel-blob 0.5.1 exposes if_match for copy/delete but not put.
        # Use the Blob SDK's PUT protocol for the two conditional news writes.
        request = Request("https://vercel.com/api/blob?" + urlencode({"pathname": path}), data=data,
                          method="PUT", headers={"Authorization": "Bearer " + config("BLOB_READ_WRITE_TOKEN"),
                          "Content-Type": mime, "x-content-type": mime, "x-api-version": "12",
                          "x-vercel-blob-access": "public", "x-allow-overwrite": "1",
                          "x-add-random-suffix": "0", "x-cache-control-max-age": "60", "x-if-match": etag})

        def write():
            try:
                with build_opener(NoRedirect()).open(request, timeout=10) as response:
                    if response.status not in (200, 201):
                        raise Failure("NEWS_BLOB_WRITE_FAILED")
            except HTTPError as error:
                with error:
                    if error.code == 412:
                        raise Failure("BLOB_CONFLICT", 409) from None
                    raise Failure("NEWS_BLOB_WRITE_FAILED", transient=error.code in (408, 429, 500, 502, 503, 504)) from None
            except (URLError, OSError, TimeoutError):
                raise Failure("NEWS_BLOB_WRITE_CONNECTION", transient=True) from None

        try:
            retry(write)
        except Failure as error:
            if error.code != "BLOB_CONFLICT" or self.read(path)[0] != data:
                raise


class News:
    def __init__(self, store=None, fetch=None, production=None):
        self.store = store if store is not None else NewsStore()
        self.fetch = fetch or image_available
        self.production = (os.environ.get("VERCEL_ENV") == "production") if production is None else production
        self.root = "haberler-kktc-news/v1/" + ("live/" if self.production else "preview/")
        self.catalog = self.root + "catalog.json"

    def read(self, path):
        data, tag = self.store.read(path)
        return (parse_json(data, "NEWS_STORAGE") if data else {}), tag

    def fixed_write(self, path, data, mime):
        try:
            self.store.put(path, data, mime)
        except Failure as error:
            if error.code != "BLOB_CONFLICT" or self.store.read(path)[0] != data:
                raise

    def publish(self, data, key):
        item = validate(data)
        news_id = item["external_id"]
        if key != "news:" + news_id:
            raise Failure("INVALID_NEWS_IDEMPOTENCY_KEY", 400)
        fingerprint = digest(encode(item))
        source = digest(item["source_url"].rstrip("/").encode())
        index, _ = self.read(self.catalog)
        if existing := self.check(index, news_id, fingerprint, source):
            return existing, False
        try:
            raw = self.fetch(item["media_url"], "NEWS_IMAGE")
            verify_jpeg(raw)
        except (ValueError, OSError):
            raise Failure("INVALID_NEWS_IMAGE", 422) from None
        permanent = "haberler-kktc-news/v1/assets/" + digest(raw) + ".jpg"
        self.fixed_write(permanent, raw, "image/jpeg")
        item["media_url"] = BLOB_ORIGIN + permanent
        if digest(self.fetch(item["media_url"], "NEWS_PUBLIC_IMAGE")) != digest(raw):
            raise Failure("NEWS_IMAGE_UNVERIFIED", 502, transient=True)
        record = self.root + f"articles/{news_id}/{fingerprint}.json"
        self.fixed_write(record, encode(item), "application/json")
        row = {name: item[name] for name in ("external_id", "title", "summary", "category", "media_url")}
        row.update(at=now().isoformat(timespec="seconds"), fingerprint=fingerprint, source=source)
        for _ in range(5):
            index, tag = self.read(self.catalog)
            if existing := self.check(index, news_id, fingerprint, source):
                return existing, False
            index[news_id] = row
            payload = encode(index)
            if len(payload) > 3_000_000:
                raise Failure("NEWS_CATALOG_CAPACITY", 503)
            try:
                self.store.put(self.catalog, payload, "application/json", tag)
                return row, True
            except Failure as error:
                if error.code != "BLOB_CONFLICT":
                    raise
        raise Failure("NEWS_CATALOG_BUSY", 503, transient=True)

    @staticmethod
    def check(index, news_id, fingerprint, source):
        if row := index.get(news_id):
            if row["fingerprint"] == fingerprint:
                return row
            raise Failure("NEWS_ID_CONFLICT", 409)
        if any(row["source"] == source for row in index.values()):
            raise Failure("NEWS_SOURCE_ALREADY_PUBLISHED", 409)
        return None

    def article(self, news_id):
        row = self.read(self.catalog)[0].get(valid_id(news_id))
        if not row:
            raise Failure("NEWS_NOT_FOUND", 404)
        article, _ = self.read(self.root + f"articles/{news_id}/{row['fingerprint']}.json")
        if not article:
            raise Failure("NEWS_RECORD_UNAVAILABLE", 503, transient=True)
        return {**article, **row}

    def list(self, category=None):
        rows = self.read(self.catalog)[0].values()
        return sorted((row for row in rows if not category or row["category"] == category),
                      key=lambda row: row["at"], reverse=True)

    def metricool(self, news_id, data=None):
        self.article(news_id)
        path = self.root + f"delivery/{news_id}.bin"
        cipher = AESGCM(hashlib.sha256(b"haberler-kktc/news-delivery/v1\x00" + config("MEDIA_ID_KEY").encode()).digest())
        context = path.encode()
        for _ in range(5):
            raw, tag = self.store.read(path)
            state = parse_json(cipher.decrypt(raw[:12], raw[12:], context), "NEWS_DELIVERY") if raw else {}
            if data is None:
                return state or {"stage": "pending"}
            operation = data.get("operation")
            mode = data.get("mode")
            if mode not in ("draft", "live") or (mode == "live" and not self.production):
                raise Failure("INVALID_SOCIAL_MODE", 400)
            if operation == "claim":
                if state and state["stage"] != "rejected":
                    return {**state, "claimed": False}
                updated = {"stage": "sending", "mode": mode}
            else:
                if not state or state["mode"] != mode or state["stage"] not in ("sending", "uncertain", "draft", "scheduled", "published"):
                    raise Failure("SOCIAL_STATE_CONFLICT", 409)
                if operation == "result":
                    post_id, status = str(data.get("post_id", "")), data.get("stage")
                    statuses = ("draft",) if mode == "draft" else ("scheduled", "published")
                    if not re.fullmatch(r"[1-9][0-9]{0,23}", post_id) or status not in statuses:
                        raise Failure("INVALID_SOCIAL_RESULT", 400)
                    if state.get("post_id", post_id) != post_id or (state["stage"] == "published" and status != "published"):
                        raise Failure("SOCIAL_STATE_CONFLICT", 409)
                    updated = {"stage": status, "mode": mode, "post_id": post_id, "brand_id": "7549135"}
                elif operation in ("rejected", "uncertain") and state["stage"] in ("sending", "uncertain"):
                    updated = {"stage": operation, "mode": mode}
                else:
                    raise Failure("SOCIAL_STATE_CONFLICT", 409)
            if updated == state:
                return state
            try:
                nonce = os.urandom(12)
                self.store.put(path, nonce + cipher.encrypt(nonce, encode(updated), context), "application/octet-stream", tag)
                return {**updated, "claimed": True} if operation == "claim" else updated
            except Failure as error:
                if error.code != "BLOB_CONFLICT":
                    raise
        raise Failure("SOCIAL_STATE_BUSY", 503, transient=True)
