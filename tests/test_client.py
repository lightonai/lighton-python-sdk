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


def test_api_error_has_no_index_outside_a_batch():
    """Single-action requests never carry one, which is what makes `index` readable."""
    client = make_client(lambda req: httpx.Response(404, json={"detail": "nope"}))
    with pytest.raises(exc.NotFoundError) as excinfo:
        client.ask("q")
    assert excinfo.value.index is None
    assert "action" not in str(excinfo.value)


def test_api_error_carries_the_batch_action_index():
    """Index 0 must survive: it is a real position, not a falsy sentinel."""
    client = make_client(
        lambda req: httpx.Response(400, json={"detail": "unknown type", "index": 0})
    )
    with pytest.raises(exc.LightOnAPIError) as excinfo:
        client.ask("q")
    assert excinfo.value.index == 0
    assert "(action 0)" in str(excinfo.value)


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


# --- raw (binary) responses -------------------------------------------------
# The download/thumbnail endpoints serve files, not JSON. They stay on the
# one _request so auth, error mapping, the 429 cooldown and the rate gate are
# shared; `raw` only skips the JSON parse.


def test_raw_returns_bytes_without_parsing_json():
    png = b"\x89PNG\r\n\x1a\n not json at all"
    client = make_client(lambda req: httpx.Response(200, content=png))

    got = client._request("GET", "/api/v3/files/7/download", raw=True)

    assert got == png
    assert isinstance(got, bytes)


def test_raw_would_have_raised_without_the_flag():
    # Same body, parsed: the guarantee is that `raw` is what makes it work.
    client = make_client(lambda req: httpx.Response(200, content=b"%PDF-1.7 binary"))
    with pytest.raises(exc.MalformedResponseError):
        client._request("GET", "/api/v3/files/7/download")


def test_raw_still_maps_errors_to_exceptions():
    # Errors stay JSON even on a binary endpoint, and must still raise.
    client = make_client(
        lambda req: httpx.Response(404, json={"detail": "No thumbnail available"})
    )
    with pytest.raises(exc.NotFoundError):
        client._request("GET", "/api/v3/files/7/thumbnail", raw=True)


def test_raw_still_retries_a_429(monkeypatch):
    monkeypatch.setattr(_client_mod.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"detail": "slow down"})
        return httpx.Response(200, content=b"%PDF-")

    client = make_client(handler, rate_limit_retries=2)
    assert client._request("GET", "/api/v3/files/7/download", raw=True) == b"%PDF-"
    assert calls["n"] == 2, "the cooldown retry must cover binary endpoints too"


def test_raw_empty_body_is_empty_bytes_not_none():
    # The JSON path turns an empty 2xx into None; the bytes path must not.
    client = make_client(lambda req: httpx.Response(200, content=b""))
    assert client._request("GET", "/api/v3/files/7/download", raw=True) == b""


# --- maintenance windows ----------------------------------------------------
# A 503 from the maintenance middleware is worth retrying later; a 503 from a
# crash is not. They arrive on the same status code, so the body tells them apart.

_MAINTENANCE_BODY = {
    "detail": "System is under maintenance.",
    "error": "service_maintenance",
    "mode": "full_shutdown",
    "reason": "database migration",
    "started_at": "2026-09-15T08:30:00Z",
    "endpoint_category_names": ["search", "ingestion"],
}


def test_maintenance_503_raises_a_dedicated_error_with_its_fields():
    client = make_client(lambda req: httpx.Response(503, json=_MAINTENANCE_BODY))

    with pytest.raises(exc.MaintenanceError) as excinfo:
        client.ask("q")

    e = excinfo.value
    assert e.mode == "full_shutdown"
    assert e.reason == "database migration"
    assert e.started_at is not None and e.started_at.year == 2026
    assert e.endpoint_categories == ["search", "ingestion"]
    assert e.status_code == 503
    assert e.body == _MAINTENANCE_BODY  # the untouched payload is still there
    assert "System is under maintenance." in str(e)


def test_maintenance_error_is_still_a_server_error():
    # Subclassing keeps existing `except ServerError` handlers working.
    client = make_client(lambda req: httpx.Response(503, json=_MAINTENANCE_BODY))
    with pytest.raises(exc.ServerError):
        client.ask("q")
    assert issubclass(exc.MaintenanceError, exc.ServerError)


def test_a_plain_503_stays_a_server_error():
    client = make_client(lambda req: httpx.Response(503, json={"detail": "boom"}))
    with pytest.raises(exc.ServerError) as excinfo:
        client.ask("q")
    assert type(excinfo.value) is exc.ServerError, (
        "a crash must not read as maintenance"
    )


def test_maintenance_survives_a_missing_or_unparsable_timestamp():
    # reason/started_at are optional; a bad timestamp must not break the raise.
    body = {"detail": "down", "error": "service_maintenance", "mode": "warning_banner"}
    client = make_client(lambda req: httpx.Response(503, json=body))
    with pytest.raises(exc.MaintenanceError) as excinfo:
        client.ask("q")
    assert excinfo.value.started_at is None
    assert excinfo.value.reason is None
    assert excinfo.value.endpoint_categories == []  # empty means every endpoint

    client = make_client(
        lambda req: httpx.Response(503, json={**body, "started_at": "not a date"})
    )
    with pytest.raises(exc.MaintenanceError) as excinfo:
        client.ask("q")
    assert excinfo.value.started_at is None
    assert excinfo.value.body["started_at"] == "not a date"  # raw value preserved


def test_maintenance_is_not_retried_like_a_429(monkeypatch):
    # 5xx is deliberately not retried: the window outlasts any cooldown we'd wait.
    monkeypatch.setattr(_client_mod.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, json=_MAINTENANCE_BODY)

    with pytest.raises(exc.MaintenanceError):
        make_client(handler, rate_limit_retries=3).ask("q")
    assert calls["n"] == 1
