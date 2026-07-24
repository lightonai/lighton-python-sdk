"""LightOn client core: auth, error mapping, transport — against a mocked transport.

Per-verb request/response tests live in test_ask.py / test_search.py / test_parse.py.
"""

import httpx
import pytest

import lighton._client as _client_mod
from lighton import LightOn, LightOnConfiguration
from lighton import exceptions as exc
from lighton._client import _RateGate


def make_client(handler, **cfg) -> LightOn:
    # rate_limit_retries=0 so mapping tests see the single-shot response; pacing off so
    # tests don't sleep on the gate (its behavior is covered by test_rate_gate_*). Both
    # are overridable by the retry-behavior tests below.
    cfg.setdefault("rate_limit_retries", 0)
    cfg.setdefault("max_requests_per_minute", None)
    return LightOn(
        "k",
        config=LightOnConfiguration(transport=httpx.MockTransport(handler), **cfg),
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

    LightOn(
        config=LightOnConfiguration(
            transport=httpx.MockTransport(handler), max_requests_per_minute=None
        )
    ).ask("q")
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


# --- rate-limit retry + pacing ---------------------------------------------
def test_rate_limit_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(_client_mod.time, "sleep", lambda _s: None)  # no real waiting
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={})
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler, rate_limit_retries=2)
    assert client._request("GET", "/x") == {"ok": True}
    assert calls["n"] == 2  # one 429, then a successful retry


def test_rate_limit_retries_exhausted_raises(monkeypatch):
    monkeypatch.setattr(_client_mod.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={"detail": "nope"})

    client = make_client(handler, rate_limit_retries=2)
    with pytest.raises(exc.RateLimitError):
        client._request("GET", "/x")
    assert calls["n"] == 3  # initial + 2 retries


def test_rate_limit_defaults_to_1000_and_is_overridable():
    # Default: a gate is installed (1000/min for most endpoints).
    assert LightOn("k")._gate is not None
    # Explicit None disables pacing.
    assert (
        LightOn("k", config=LightOnConfiguration(max_requests_per_minute=None))._gate
        is None
    )


def test_rate_gate_paces_requests():
    now = {"t": 0.0}
    slept: list[float] = []
    gate = _RateGate(60, sleep=slept.append, monotonic=lambda: now["t"])  # 1 req/s

    gate.acquire()  # first call: nothing scheduled yet, no wait
    assert slept == []
    now["t"] = 0.1  # 0.1s elapsed, but the interval is 1.0s
    gate.acquire()
    assert slept[-1] == pytest.approx(0.9, abs=0.01)
