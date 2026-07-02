"""LightOn client: auth, verb routing, error mapping — against a mocked transport."""

import json

import httpx
import pytest

from lighton import LightOn, LightOnConfiguration
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
        return httpx.Response(200, json={})

    LightOn(config=LightOnConfiguration(transport=httpx.MockTransport(handler))).ask()
    assert seen["auth"] == "Bearer envkey"


@pytest.mark.parametrize(
    "verb,path",
    [
        ("ask", "/api/v3/ask"),
        ("search", "/api/v3/search"),
        ("parse", "/api/v3/parse"),
        ("extract", "/api/v3/extract"),
    ],
)
def test_verb_routing_and_payload(verb, path):
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"ok": True})

    result = getattr(make_client(handler), verb)(q="hello")
    assert result == {"ok": True}
    assert seen["method"] == "POST"
    assert seen["path"] == path
    assert seen["body"] == {"q": "hello"}


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
        client.ask()
    assert type(excinfo.value) is expected
    assert excinfo.value.status_code == status


def test_empty_2xx_returns_none():
    client = make_client(lambda req: httpx.Response(204))
    assert client._request("DELETE", "/x") is None


def test_malformed_json_2xx_raises():
    client = make_client(lambda req: httpx.Response(200, content=b"not json"))
    with pytest.raises(exc.MalformedResponseError):
        client.ask()


def test_transport_error_is_wrapped():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(exc.LightOnConnectionError):
        make_client(handler).ask()


def test_context_manager_closes():
    client = make_client(lambda req: httpx.Response(200, json={}))
    with client as c:
        assert c is client
    assert client._http.is_closed
