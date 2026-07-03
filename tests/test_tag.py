"""Active-record Tag: list/create/delete work; get/refresh raise (no single GET)."""

import json

import httpx
import pytest

from lighton import LightOn, Tag
from lighton.tag import _BASE
from lighton.types import LightOnConfiguration


@pytest.fixture
def client():
    def handler(request: httpx.Request) -> httpx.Response:
        m, path = request.method, request.url.path
        if m == "POST" and path == _BASE:
            body = json.loads(request.content)
            return httpx.Response(201, json={"id": 5, "document_count": 0, **body})
        if m == "DELETE":
            return httpx.Response(204)
        if m == "GET" and path == _BASE:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"id": 1, "name": "legal", "auto_assign": True},
                        {"id": 2, "name": "hr", "auto_assign": False},
                    ],
                    "next": None,
                },
            )
        return httpx.Response(200, json={})

    return LightOn(
        "k", config=LightOnConfiguration(transport=httpx.MockTransport(handler))
    )


def test_create_binds_and_populates(client):
    tag = Tag(name="legal", description="Legal docs", auto_assign=False).create(client)
    assert tag.id == 5 and tag.name == "legal" and tag.auto_assign is False


def test_list(client):
    assert [(t.id, t.name) for t in Tag.list(client)] == [(1, "legal"), (2, "hr")]


def test_delete_clears_id(client):
    tag = Tag(name="legal", description="x").create(client)
    tag.delete()
    assert tag.id is None


def test_get_and_refresh_unsupported(client):
    with pytest.raises(NotImplementedError):
        Tag.get(client, 1)
    with pytest.raises(NotImplementedError):
        Tag(name="legal", description="x").create(client).refresh()
