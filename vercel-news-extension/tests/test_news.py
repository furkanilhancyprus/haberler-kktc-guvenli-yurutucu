import io
import os
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

from media_service.news import BLOB_ORIGIN, News, NewsStore
from media_service import news_page
from media_service.providers import Failure


class MemoryStore:
    def __init__(self):
        self.items = {}
        self.revision = 0

    def read(self, key):
        return self.items.get(key, (None, None))

    def put(self, key, value, content_type, etag=None):
        if self.read(key)[1] != etag:
            raise Failure("BLOB_CONFLICT", 409)
        self.revision += 1
        self.items[key] = value, str(self.revision)


class NewsTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        image = io.BytesIO()
        Image.new("RGB", (1080, 1350), "red").save(image, "JPEG")
        self.image = image.getvalue()
        self.item = {"external_id": "hkk-technical-test", "title": "<script> & Haber", "content": "Gövde\n\nSon satır",
                     "summary": "Özet", "category": "Dünya", "source_name": "Kaynak",
                     "source_url": "https://example.com/news/exact", "tags": ["Dünya"],
                     "status": "published", "media_url": BLOB_ORIGIN + "haberler-kktc-temp/v1/images/" + "0" * 40 + ".jpg"}
        self.news = News(self.store, lambda url, prefix: self.image, production=False)
        self.key = "news:" + self.item["external_id"]

    def test_validate_before_fetch(self):
        with self.assertRaisesRegex(Failure, "INVALID_NEWS_MEDIA"):
            self.news.publish({**self.item, "media_url": "https://example.com/image.jpg"}, self.key)
        with self.assertRaisesRegex(Failure, "INVALID_NEWS_FIELDS"):
            self.news.publish({**self.item, "title": ""}, self.key)
        self.assertFalse(self.store.items)

    def test_permanent_copy_retry_and_source_duplicate(self):
        first, created = self.news.publish(self.item, self.key)
        self.assertTrue(created)
        self.assertIn("/v1/assets/", first["media_url"])
        self.assertEqual(self.store.read(first["media_url"].removeprefix(BLOB_ORIGIN))[0], self.image)
        self.assertEqual(self.news.publish(self.item, self.key), (first, False))
        with self.assertRaisesRegex(Failure, "NEWS_ID_CONFLICT"):
            self.news.publish({**self.item, "summary": "Değişti"}, self.key)
        with self.assertRaisesRegex(Failure, "NEWS_SOURCE_ALREADY_PUBLISHED"):
            self.news.publish({**self.item, "external_id": "hkk-another-test"}, "news:hkk-another-test")
        self.assertEqual(self.news.article(self.item["external_id"])["content"], self.item["content"])
        self.assertEqual(self.news.list("dunya"), [first])
        self.assertFalse(News(self.store, production=True).list())

    @patch.dict(os.environ, {"MEDIA_ID_KEY": "test-secret-for-encrypted-provider-status"})
    def test_claim_reconcile_state_and_preview_live_denied(self):
        self.news.publish(self.item, self.key)
        news_id = self.item["external_id"]
        draft = {"operation": "claim", "mode": "draft"}
        self.assertTrue(self.news.metricool(news_id, draft)["claimed"])
        self.assertFalse(self.news.metricool(news_id, draft)["claimed"])
        self.news.metricool(news_id, {"operation": "uncertain", "mode": "draft"})
        self.assertFalse(self.news.metricool(news_id, draft)["claimed"])
        result = {"operation": "result", "mode": "draft", "stage": "draft", "post_id": "18823419"}
        self.news.metricool(news_id, result)
        self.assertEqual(self.news.metricool(news_id)["post_id"], "18823419")
        self.assertNotIn(b"18823419", self.store.read(self.news.root + f"delivery/{news_id}.bin")[0])
        with self.assertRaisesRegex(Failure, "INVALID_SOCIAL_MODE"):
            self.news.metricool(news_id, {"operation": "claim", "mode": "live"})

    def test_server_rendered_article_is_escaped(self):
        self.news.publish(self.item, self.key)
        row = self.news.article(self.item["external_id"])
        fallback = ('<head><title>Previous</title><meta name="robots" content="noindex"></head>'
                    '<main id="main">old article</main>')
        with patch.object(news_page, "template", return_value=fallback):
            page = news_page.article(row, "https://preview.invalid", False)
        self.assertIn("&lt;script&gt; &amp; Haber", page)
        self.assertIn("https://preview.invalid/haber/hkk-technical-test", page)
        self.assertIn("noindex", page)
        self.assertNotIn("old article", page)

    @patch.dict(os.environ, {"BLOB_READ_WRITE_TOKEN": "test-blob-token"})
    @patch("media_service.news.build_opener")
    def test_conditional_blob_update_supplies_the_destination_etag(self, opener):
        response = MagicMock()
        response.__enter__.return_value.status = 200
        transport = opener.return_value
        transport.open.return_value = response
        NewsStore().put("test/catalog.json", b"{}", "application/json", '"expected-etag"')
        request = transport.open.call_args.args[0]
        self.assertEqual(request.get_method(), "PUT")
        self.assertEqual(request.get_header("X-if-match"), '"expected-etag"')
        self.assertEqual(request.get_header("X-allow-overwrite"), "1")
