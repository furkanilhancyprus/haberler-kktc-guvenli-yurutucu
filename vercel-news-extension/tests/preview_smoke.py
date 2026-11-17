"""Run only against the protected preview, using a local test JPEG."""
import argparse
import json
from pathlib import Path

from news_client import Client, PRODUCTION
from media_service.providers import Failure


def main():
    parser = argparse.ArgumentParser()
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--image", type=Path)
    inputs.add_argument("--uploaded-url")
    parser.add_argument("--id", required=True)
    args = parser.parse_args()
    client = Client()
    if client.origin == PRODUCTION:
        raise RuntimeError("This synthetic test requires a preview deployment.")
    story = {"external_id": args.id, "title": "Teknik önizleme: haber yayın API testi",
             "content": "Bu içerik yalnızca korumalı önizlemede yapılan teknik bir testtir.",
             "summary": "Teknik test", "category": "Gündem", "source_name": "Haberler KKTC test kaydı",
             "source_url": PRODUCTION + "/haber/" + args.id, "tags": ["Teknik test"],
             "status": "published", "media_url": "https://example.com/invalid.jpg"}
    rejected = (({}, False, 401), ({}, True, 400), (story, True, 400))
    for payload, authenticated, expected in rejected:
        try:
            client.request("/api/news/publish", payload=payload, authenticated=authenticated, key="news:" + args.id)
        except Failure as error:
            if error.status != expected:
                raise RuntimeError(f"Expected HTTP {expected}, received HTTP {error.status}") from error
        else:
            raise RuntimeError(f"Expected HTTP {expected}, received success")
    if args.uploaded_url:
        story["media_url"] = args.uploaded_url
    first = client.publish(story, args.image)
    second = client.publish(story, args.image)
    if first["news_url"] != second["news_url"] or second["created"]:
        raise RuntimeError("Duplicate published")
    path = f"/haber/{args.id}".encode()
    for route in ("/", "/son-haberler", "/kategori/gundem"):
        content, mime = client.request(route)
        if mime != "text/html" or path not in content:
            raise RuntimeError(f"Story missing from {route}")
    print(json.dumps({**first, "checked": ["unauthorized", "invalid-data", "invalid-image", "article",
                                          "image", "duplicate", "home", "archive", "category"]}))


if __name__ == "__main__":
    main()
