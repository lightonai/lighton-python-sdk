"""parse verb: url → JSON body, path → multipart, and path-XOR-url validation."""

import json

import httpx
import pytest

from lighton import LightOn, LightOnConfiguration


def make_client(handler) -> LightOn:
    return LightOn(
        "k", config=LightOnConfiguration(transport=httpx.MockTransport(handler))
    )


def _parse_body(doc_id: str, file_size: int) -> dict:
    return {
        "id": doc_id,
        "status": "completed",
        "created_at": "2026-01-01T00:00:00Z",
        "completed_at": "2026-01-01T00:00:01Z",
        "processing_time_ms": 5,
        "document": {
            "filename": "d.pdf",
            "page_count": 1,
            "file_size_bytes": file_size,
            "mime_type": "application/pdf",
        },
        "result": {"pages": []},
        "usage": {"pages_processed": 1},
    }


def test_parse_url_sends_json():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=_parse_body("p1", 10))

    resp = make_client(handler).parse(url="https://example.com/d.pdf")
    assert resp.id == "p1"
    assert seen["body"] == {"document": "https://example.com/d.pdf"}


def test_parse_requires_exactly_one_arg():
    client = make_client(lambda req: httpx.Response(200))
    with pytest.raises(ValueError):
        client.parse()
    with pytest.raises(ValueError):
        client.parse(path="d.pdf", url="https://example.com/d.pdf")


def test_parse_path_sends_multipart(tmp_path):
    f = tmp_path / "d.pdf"
    f.write_bytes(b"%PDF-1.4")
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["ctype"] = req.headers.get("content-type", "")
        return httpx.Response(200, json=_parse_body("p2", 8))

    resp = make_client(handler).parse(path=f)
    assert resp.id == "p2"
    assert seen["ctype"].startswith("multipart/form-data")
