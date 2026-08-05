"""parse verb: url → JSON body, path → multipart, and path-XOR-url validation."""

import json

import httpx
import pytest

from lighton import ExecMode, LightOn, LightOnConfiguration


def make_client(handler) -> LightOn:
    return LightOn(
        "k",
        config=LightOnConfiguration(
            transport=httpx.MockTransport(handler), max_requests_per_minute=None
        ),
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


def test_parse_async_returns_job_and_polls_in_place():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            seen["body"] = json.loads(req.content)
            return httpx.Response(
                202,
                json={
                    "id": "parse_Kg",
                    "status": "pending",
                    "created_at": "2026-01-01T00:00:00Z",
                },
            )
        assert req.url.path == "/api/v3/parse/parse_Kg"  # GET poll
        body = _parse_body("parse_Kg", 8)
        body["error"] = None
        return httpx.Response(200, json=body)

    job = make_client(handler).parse(
        url="https://example.com/d.pdf", mode=ExecMode.ASYNC
    )
    assert job.id == "parse_Kg" and not job.succeeded and not job.done
    assert seen["body"]["options"] == {"async": True}

    same = job.poll()  # updates in place, returns self
    assert same is job
    assert job.succeeded and job.done
    assert job.result is not None and job.result.pages == []


def test_parse_async_wait_returns_finished_job():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.method == "POST"  # already terminal, no poll needed
        return httpx.Response(200, json=_parse_body("parse_Kg", 8))

    job = make_client(handler).parse(
        url="https://example.com/d.pdf", mode=ExecMode.ASYNC, wait=True
    )
    assert job.done and job.succeeded and job.result is not None


def test_parse_wait_requires_async_mode():
    client = make_client(lambda req: httpx.Response(200, json=_parse_body("p1", 8)))
    with pytest.raises(ValueError, match="wait=True"):
        # wait without ASYNC is also a static error, hence the ignore
        client.parse(url="https://example.com/d.pdf", wait=True)  # ty: ignore[no-matching-overload]
