"""Active-record ApiKey lifecycle, secret handling, and scopes (mocked transport)."""

import json
from datetime import datetime, timezone

import httpx
import pytest

from lighton import ApiKey, ApiKeyScope, LightOn, LightOnConfiguration, Role
from lighton.apikey import _BASE


@pytest.fixture
def client():
    store = {
        "id": "k_1",
        "name": "ci",
        "prefix": "lo_abc",
        "expires_at": None,
        "scopes": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        m, path = request.method, request.url.path
        if m == "POST" and path == _BASE:
            store["name"] = json.loads(request.content)["name"]
            return httpx.Response(201, json={**store, "key": "secret-xyz"})
        if m == "PATCH":
            store.update(json.loads(request.content))
            return httpx.Response(200, json=store)  # note: no "key"
        if m == "DELETE":
            return httpx.Response(204)
        if m == "GET" and "page=2" in str(request.url):
            return httpx.Response(
                200, json={"results": [{"id": "k_2", "name": "b"}], "next": None}
            )
        if m == "GET" and path == _BASE:
            nxt = "https://api.lighton.ai/api/v3/keys?page=2"
            return httpx.Response(
                200, json={"results": [{"id": "k_1", "name": "a"}], "next": nxt}
            )
        return httpx.Response(200, json=store)

    return LightOn(
        "k", config=LightOnConfiguration(transport=httpx.MockTransport(handler))
    )


def test_create_returns_secret_once(client):
    key = ApiKey(name="ci").create(client)
    assert key.id == "k_1"
    assert key.prefix == "lo_abc"
    assert key.key is not None
    assert key.key.get_secret_value() == "secret-xyz"  # plaintext only on create


def test_refresh_preserves_in_memory_secret(client):
    key = ApiKey(name="ci").create(client)
    key.refresh()  # GET response omits "key"
    assert key.key is not None
    assert key.key.get_secret_value() == "secret-xyz"  # not wiped by the response


def test_list_follows_pagination(client):
    assert [k.id for k in ApiKey.list(client)] == ["k_1", "k_2"]


def test_methods_fail_after_delete(client):
    key = ApiKey(name="ci").create(client)
    key.delete()
    assert key.id is None
    with pytest.raises(ValueError):
        key.save()


def test_create_serializes_scopes_and_expiry():
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "k_1", "name": "ci", "scopes": []})

    client = LightOn(
        "k", config=LightOnConfiguration(transport=httpx.MockTransport(handler))
    )
    ApiKey(
        name="ci",
        expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        scopes=[ApiKeyScope(workspace_id=3, role=Role.viewer)],
    ).create(client)

    assert sent["body"]["scopes"] == [{"workspace_id": 3, "role": "viewer"}]
    assert sent["body"]["expires_at"].startswith("2030-01-01")
