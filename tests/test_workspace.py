"""Active-record Workspace lifecycle + pagination, against a mocked transport."""

import json

import httpx
import pytest

from lighton import LightOn, Workspace
from lighton.types import LightOnConfiguration
from lighton.workspace import _BASE


@pytest.fixture
def client():
    store = {"id": 7, "name": "Legal", "description": ""}

    def handler(request: httpx.Request) -> httpx.Response:
        m, path = request.method, request.url.path
        if m == "POST" and path == _BASE:
            return httpx.Response(201, json={**store, "workspace_type": "standard"})
        if m == "PATCH":
            store.update(json.loads(request.content))
            return httpx.Response(200, json=store)
        if m == "DELETE":
            return httpx.Response(204)
        if m == "GET" and "page=2" in str(request.url):
            return httpx.Response(
                200, json={"results": [{"id": 2, "name": "B"}], "next": None}
            )
        if m == "GET" and path == _BASE:
            nxt = "https://api.lighton.ai/api/v3/workspaces?page=2"
            return httpx.Response(
                200, json={"results": [{"id": 1, "name": "A"}], "next": nxt}
            )
        return httpx.Response(200, json=store)

    return LightOn(
        "k",
        config=LightOnConfiguration(
            transport=httpx.MockTransport(handler), max_requests_per_minute=None
        ),
    )


def test_create_binds_and_populates(client):
    ws = Workspace(name="Legal").create(client)
    assert ws.id == 7
    assert ws.workspace_type == "standard"


def test_save_persists_edits(client):
    ws = Workspace(name="Legal").create(client)
    ws.name = "Legal EU"
    ws.save()
    assert ws.name == "Legal EU"


def test_list_follows_pagination(client):
    assert [w.id for w in Workspace.list(client)] == [1, 2]


def test_methods_fail_after_delete(client):
    ws = Workspace(name="Legal").create(client)
    ws.delete()
    assert ws.id is None
    with pytest.raises(ValueError):
        ws.save()
