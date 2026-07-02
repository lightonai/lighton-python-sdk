"""LightOn client: auth, verb routing, error mapping — against a mocked transport."""

import json

import httpx
import pytest

from lighton import LightOn, LightOnConfiguration, SearchMode, Workspace
from lighton import exceptions as exc


def make_client(handler) -> LightOn:
    return LightOn(
        "k", config=LightOnConfiguration(transport=httpx.MockTransport(handler))
    )


def test_requires_api_key(monkeypatch):
    monkeypatch.delenv("LIGHTON_API_KEY", raising=False)
    with pytest.raises(ValueError):
        LightOn()


def test_api_key_from_env(monkeypatch):
    monkeypatch.setenv("LIGHTON_API_KEY", "envkey")
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["auth"] = req.headers.get("authorization")
        return httpx.Response(200, json={"results": [], "answer": ""})

    LightOn(config=LightOnConfiguration(transport=httpx.MockTransport(handler))).ask(
        "q"
    )
    assert seen["auth"] == "Bearer envkey"


def test_ask_request_and_typed_response():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"results": [], "answer": "42"})

    # workspaces/files accept objects or bare ids, coerced to workspace_id/file_id.
    resp = make_client(handler).ask(
        "meaning?", workspaces=[Workspace(id=1, name="w"), 2]
    )
    assert resp.answer == "42"
    assert seen["path"] == "/api/v3/ask"
    # None params are dropped so the server applies its own defaults.
    assert seen["body"] == {"query": "meaning?", "workspace_id": [1, 2]}


def test_search_request_and_typed_response():
    def handler(req: httpx.Request) -> httpx.Response:
        assert json.loads(req.content) == {"query": "q", "mode": "vision"}
        return httpx.Response(200, json={"results": []})

    resp = make_client(handler).search("q", mode=SearchMode.vision)
    assert resp.results == []


def test_parse_url_sends_json():
    seen = {}
    body = {
        "id": "p1",
        "status": "completed",
        "created_at": "2026-01-01T00:00:00Z",
        "completed_at": "2026-01-01T00:00:01Z",
        "processing_time_ms": 5,
        "document": {
            "filename": "d.pdf",
            "page_count": 1,
            "file_size_bytes": 10,
            "mime_type": "application/pdf",
        },
        "result": {"pages": []},
        "usage": {"pages_processed": 1},
    }

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=body)

    resp = make_client(handler).parse(url="https://example.com/d.pdf")
    assert resp.id == "p1"
    assert seen["body"] == {"document": "https://example.com/d.pdf"}


def test_parse_requires_exactly_one_arg(tmp_path):
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
        return httpx.Response(
            200,
            json={
                "id": "p2",
                "status": "completed",
                "created_at": "2026-01-01T00:00:00Z",
                "completed_at": "2026-01-01T00:00:01Z",
                "processing_time_ms": 5,
                "document": {
                    "filename": "d.pdf",
                    "page_count": 1,
                    "file_size_bytes": 8,
                    "mime_type": "application/pdf",
                },
                "result": {"pages": []},
                "usage": {"pages_processed": 1},
            },
        )

    resp = make_client(handler).parse(path=f)
    assert resp.id == "p2"
    assert seen["ctype"].startswith("multipart/form-data")


@pytest.mark.parametrize(
    "status,expected",
    [
        (401, exc.AuthenticationError),
        (403, exc.AuthenticationError),
        (404, exc.NotFoundError),
        (429, exc.RateLimitError),
        (500, exc.ServerError),
        (503, exc.ServerError),
        (418, exc.LightOnAPIError),  # unmapped 4xx -> base API error
    ],
)
def test_error_mapping(status, expected):
    client = make_client(lambda req: httpx.Response(status, json={"detail": "nope"}))
    with pytest.raises(expected) as excinfo:
        client.ask("q")
    assert type(excinfo.value) is expected
    assert excinfo.value.status_code == status


def test_empty_2xx_returns_none():
    client = make_client(lambda req: httpx.Response(204))
    assert client._request("DELETE", "/x") is None


def test_malformed_json_2xx_raises():
    client = make_client(lambda req: httpx.Response(200, content=b"not json"))
    with pytest.raises(exc.MalformedResponseError):
        client.ask("q")


def test_transport_error_is_wrapped():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(exc.LightOnConnectionError):
        make_client(handler).ask("q")


def test_context_manager_closes():
    client = make_client(lambda req: httpx.Response(200, json={}))
    with client as c:
        assert c is client
    assert client._http.is_closed
