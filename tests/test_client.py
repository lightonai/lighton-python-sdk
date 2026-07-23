"""LightOn client core: auth, error mapping, transport — against a mocked transport.

Per-verb request/response tests live in test_ask.py / test_search.py / test_parse.py.
"""

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
        return httpx.Response(200, json={"results": [], "answer": ""})

    LightOn(config=LightOnConfiguration(transport=httpx.MockTransport(handler))).ask(
        "q"
    )
    assert seen["auth"] == "Bearer envkey"


@pytest.mark.parametrize(
    "status,expected",
    [
        (401, exc.AuthenticationError),
        (403, exc.PermissionDeniedError),
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


def test_rate_limit_exposes_retry_after():
    client = make_client(
        lambda req: httpx.Response(
            429, json={"detail": "slow down"}, headers={"Retry-After": "30"}
        )
    )
    with pytest.raises(exc.RateLimitError) as excinfo:
        client.ask("q")
    assert excinfo.value.retry_after == 30.0


def test_rate_limit_without_header_has_none_retry_after():
    client = make_client(lambda req: httpx.Response(429, json={"detail": "slow down"}))
    with pytest.raises(exc.RateLimitError) as excinfo:
        client.ask("q")
    assert excinfo.value.retry_after is None


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
