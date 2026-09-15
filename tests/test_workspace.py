"""Active-record Workspace lifecycle + pagination, against a mocked transport."""

import json

import httpx
import pytest

from lighton import LightOn, Role, Workspace
from lighton.types import LightOnConfiguration
from lighton.workspace import _BASE


def _make_client(handler) -> LightOn:
    return LightOn(
        "k",
        config=LightOnConfiguration(
            transport=httpx.MockTransport(handler), max_requests_per_minute=None
        ),
    )


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

    return _make_client(handler)


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


def _listing(row):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/7"):  # the detail endpoint omits `taxonomy`
            return httpx.Response(
                200, json={"id": 7, "name": "Docs", "user_role": "owner"}
            )
        return httpx.Response(200, json={"results": [row], "next": None})

    return _make_client(handler)


def test_list_parses_taxonomy_role_and_sync():
    row = {
        "id": 7,
        "name": "Docs",
        "user_role": "editor",
        "taxonomy": {
            "classified_files_rate": 0.75,
            "root_content_types": [
                {"path": "legal", "label": "Legal", "count": 3},
                {"path": "finance", "label": "Finance", "count": 1},
            ],
        },
        "sync": {
            "name": "sharepoint-main",
            "datasource_type": "sharepoint",
            "last_status": "success",
            "failed_files_count": 2,
            "updated_at": "2026-09-15T10:00:00Z",
        },
    }
    [ws] = Workspace.list(_listing(row))

    assert ws.user_role is Role.editor
    assert ws.taxonomy is not None
    assert ws.taxonomy.classified_files_rate == 0.75
    assert [(r.path, r.count) for r in ws.taxonomy.root_content_types] == [
        ("legal", 3),
        ("finance", 1),
    ]
    assert ws.sync is not None
    assert ws.sync.datasource_type == "sharepoint" and ws.sync.failed_files_count == 2
    assert ws.sync.updated_at is not None and ws.sync.updated_at.year == 2026


def test_blank_user_role_reads_as_none():
    # The API sends "" for "no role", which is not a Role member.
    [ws] = Workspace.list(_listing({"id": 7, "name": "Docs", "user_role": ""}))
    assert ws.user_role is None


def test_taxonomy_survives_a_refresh():
    # Only list() returns taxonomy; the detail endpoint omits the key, and _absorb
    # overwrites only what came back, so refreshing must not clear it.
    row = {
        "id": 7,
        "name": "Docs",
        "taxonomy": {
            "classified_files_rate": 1.0,
            "root_content_types": [{"path": "legal", "label": "Legal", "count": 1}],
        },
    }
    [ws] = Workspace.list(_listing(row))
    assert ws.taxonomy is not None
    before = ws.taxonomy

    ws.refresh()

    assert ws.taxonomy == before, "refresh() wiped a field its endpoint never returns"
    assert ws.user_role is Role.owner  # ...while still absorbing what it does return


def test_absent_taxonomy_and_sync_are_none():
    [ws] = Workspace.list(_listing({"id": 7, "name": "Docs"}))
    assert ws.taxonomy is None and ws.sync is None and ws.user_role is None
