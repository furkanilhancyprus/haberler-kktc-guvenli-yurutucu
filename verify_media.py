import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

UPLOAD = "https://haberler-kktc.vercel.app/api/media/upload"
BLOB_HOST = "fva2uclbr7ema1sw.public.blob.vercel-storage.com"
TEST_KEY = "news:github-actions-media-probe:v1"
MAX_BYTES = 4_000_000


class DirectOnly(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def verify_jpeg(data):
    if len(data) < 10 or data[:2] != b"\xff\xd8" or data[-2:] != b"\xff\xd9":
        raise ValueError("INVALID_JPEG")

    cursor = 2
    dimensions = None
    while cursor + 4 <= len(data):
        if data[cursor] != 255:
            raise ValueError("INVALID_JPEG_MARKER")
        marker = data[cursor + 1]
        length = int.from_bytes(data[cursor + 2:cursor + 4], "big")
        end = cursor + length + 2
        if length < 2 or end > len(data):
            raise ValueError("INVALID_JPEG_SEGMENT")
        segment = data[cursor + 4:end]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3):
            if len(segment) < 6:
                raise ValueError("INVALID_JPEG_DIMENSIONS")
            dimensions = (int.from_bytes(segment[3:5], "big"), int.from_bytes(segment[1:3], "big"))
        if marker == 0xFE or 0xE0 <= marker <= 0xEF and (marker != 0xE0 or not segment.startswith(b"JFIF\0")):
            raise ValueError("METADATA_PRESENT")
        if marker == 0xDA:
            if dimensions != (1080, 1350):
                raise ValueError("INVALID_JPEG_DIMENSIONS")
            return
        cursor = end
    raise ValueError("JPEG_SCAN_MISSING")


def verify_blob_url(address, media_id):
    if not isinstance(address, str) or not isinstance(media_id, str) or not re.fullmatch(r"[0-9a-f]{40}", media_id):
        raise ValueError("INVALID_UPLOAD_RESPONSE")
    url = urlsplit(address)
    if (url.scheme != "https" or url.netloc != BLOB_HOST
            or url.path != f"/haberler-kktc-temp/v1/images/{media_id}.jpg" or url.query or url.fragment):
        raise ValueError("UNEXPECTED_BLOB_URL")


def run(check_only):
    token = os.environ.get("MEDIA_API_TOKEN")
    if not token:
        raise ValueError("MEDIA_API_TOKEN_MISSING")
    if check_only:
        data = b""
    else:
        data = Path(__file__).with_name("test-image.jpg").read_bytes()
        verify_jpeg(data)

    opener = build_opener(DirectOnly)
    request = Request(UPLOAD, data=data, method="POST", headers={
        "Content-Type": "image/jpeg",
        "Authorization": "Bearer " + token,
        "Idempotency-Key": TEST_KEY,
    })
    try:
        with opener.open(request, timeout=25) as response:
            response_status = response.status
            result = json.loads(response.read(16_000))
    except HTTPError as error:
        if check_only and error.code == 413:
            try:
                denied = json.loads(error.read(4096))
            except (ValueError, UnicodeError):
                raise ValueError("UPLOAD_CHECK_RESPONSE_INVALID") from None
            if denied.get("error") == "INVALID_REQUEST_SIZE":
                return {"authorized": True, "blob_created": False}
        raise ValueError(f"UPLOAD_HTTP_{error.code}") from None
    if check_only:
        raise ValueError("CHECK_ENDPOINT_ACCEPTED_EMPTY_BODY")
    if not isinstance(result, dict) or result.get("status") != "uploaded" or result.get("metadataClean") is not True:
        raise ValueError("INVALID_UPLOAD_RESPONSE")
    url = result.get("url")
    media_id = result.get("mediaId")
    verify_blob_url(url, media_id)
    try:
        with opener.open(url, timeout=20) as response:
            if response.headers.get_content_type() != "image/jpeg":
                raise ValueError("BLOB_CONTENT_TYPE_INVALID")
            raw = response.read(MAX_BYTES + 1)
    except HTTPError as error:
        raise ValueError(f"BLOB_HTTP_{error.code}") from None
    if len(raw) > MAX_BYTES:
        raise ValueError("BLOB_TOO_LARGE")
    verify_jpeg(raw)
    return {"http": response_status, "mediaId": media_id, "url": url, "dimensions": "1080x1350", "metadataClean": True}


if __name__ == "__main__":
    flags = argparse.ArgumentParser()
    flags.add_argument("--check-only", action="store_true")
    try:
        print(json.dumps(run(flags.parse_args().check_only)))
    except ValueError as error:
        code = str(error)
        print(code if re.fullmatch(r"[A-Z0-9_]+", code) else "INVALID_RESPONSE", file=sys.stderr)
        sys.exit(1)
    except (URLError, OSError):
        print("TRANSFER_OR_INPUT_FAILED", file=sys.stderr)
        sys.exit(1)
