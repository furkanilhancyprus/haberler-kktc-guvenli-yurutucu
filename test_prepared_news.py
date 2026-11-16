import base64
import hashlib
import io
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import prepared_news as runner


class PreparedNewsTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.news_id = "technical-transfer-probe"
        package = Path(directory.name) / self.news_id
        package.mkdir()
        self.path = package / "manifest.json"
        self.now = datetime.now(UTC)
        self.requested = (self.now + timedelta(hours=1)).astimezone(runner.CYPRUS)
        raw = Path("test-image.jpg").read_bytes()
        with Image.open(io.BytesIO(raw)) as image:
            exif = Image.Exif()
            exif[270] = "metadata sentinel"
            stream = io.BytesIO()
            image.save(stream, "JPEG", exif=exif)
        raw = stream.getvalue()
        self.packet = {
            "newsId": self.news_id, "status": "ready", "verified": True,
            "imageRightsVerified": True, "timezone": runner.ZONE,
            "imagePath": "image.jpg", "headline": "Teknik aktarım testi",
            "sourceUrls": ["https://example.org/story", "https://example.net/story"],
            "publishedAt": self.now.isoformat(), "publicationDate": self.requested.isoformat(),
            "postText": "Teknik aktarım testi", "imageSha256": hashlib.sha256(raw).hexdigest(),
            "imageBase64": base64.b64encode(raw).decode("ascii"),
        }
        self.write()

    def write(self):
        self.path.write_text(json.dumps(self.packet), encoding="utf-8")

    def test_jpeg_and_metadata(self):
        _, _, _, clean = runner.load_package(self.path, self.now)
        runner.verify_jpeg(clean)
        with Image.open(io.BytesIO(clean)) as image:
            self.assertFalse(image.getexif())
            self.assertEqual(image.size, (1080, 1350))
            self.assertNotIn("icc_profile", image.info)

    def test_image_hash_is_required(self):
        self.packet["imageSha256"] = "0" * 64
        self.write()
        with self.assertRaisesRegex(runner.TransferError, "JPEG_HASH_MISMATCH"):
            runner.load_package(self.path, self.now)

    def test_past_time_is_rejected(self):
        self.packet["publicationDate"] = (self.requested - timedelta(hours=2)).isoformat()
        self.write()
        with self.assertRaisesRegex(runner.TransferError, "INVALID_OR_EXPIRED_TIMES"):
            runner.load_package(self.path, self.now)

    def test_draft_and_ambiguous_post_recovery(self):
        url = "https://static.metricool.com/planner/fixture.jpg"
        post = runner.post_body(self.packet["postText"], self.requested, url)
        post.update(id=123, uuid="test-uuid")
        snapshots = []

        def store(news_id, record, previous=None):
            self.assertEqual(news_id, self.news_id)
            snapshots.append(dict(record))
            return "state-sha"

        def request(path, token, user, data=None):
            if data is not None:
                self.assertEqual(data, runner.post_body(self.packet["postText"], self.requested, url))
                raise runner.TransferError("METRICOOL_NETWORK_ERROR")
            self.assertTrue(path.endswith("/123"))
            return json.dumps({"data": post}).encode()

        settings = {"METRICOOL_API_TOKEN": "stub", "METRICOOL_USER_ID": "1", "MEDIA_API_TOKEN": "stub"}
        with patch.dict("os.environ", settings), patch.object(runner, "github_state", side_effect=store), \
                patch.object(runner, "calendar_match", side_effect=[None, post]), \
                patch.object(runner, "metricool", side_effect=request) as metricool, \
                patch.object(runner, "metricool_jpeg"), patch.object(runner, "normalized_media", return_value=url):
            result = runner.deliver(self.path, False)
            self.assertEqual(result["metricoolPostId"], 123)
            self.assertEqual(result["status"], "draft_verified")
            self.assertTrue(result["draft"])
            self.assertFalse(result["autoPublish"])
            self.assertEqual(snapshots[0]["status"], "draft_pending")
            self.assertEqual(sum(call.kwargs.get("data") is not None for call in metricool.call_args_list), 1)
            runner.deliver(self.path, False, snapshots[1], "state-sha")
            self.assertEqual(sum(call.kwargs.get("data") is not None for call in metricool.call_args_list), 1)

    def test_unconfirmed_pending_post_is_not_created_again(self):
        caption = self.packet["postText"]
        state = {
            "status": "draft_pending",
            "packageSha256": hashlib.sha256(runner.encode([caption, self.packet["imageSha256"]])).hexdigest(),
            "requestedDate": self.requested.isoformat(),
        }
        settings = {"METRICOOL_API_TOKEN": "stub", "METRICOOL_USER_ID": "1", "MEDIA_API_TOKEN": "stub"}
        with patch.dict("os.environ", settings), patch.object(runner, "calendar_match", return_value=None), \
                patch.object(runner, "metricool") as metricool:
            with self.assertRaisesRegex(runner.TransferError, "METRICOOL_POST_UNCERTAIN_NO_RETRY"):
                runner.deliver(self.path, False, state, "state-sha")
            metricool.assert_not_called()
