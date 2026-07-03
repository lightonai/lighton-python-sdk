"""ask verb: request shaping (workspaces/files → ids, None-drop) and typed response."""

import json

import httpx

from lighton import LightOn, LightOnConfiguration, Tag, Workspace


def make_client(handler) -> LightOn:
    return LightOn(
        "k", config=LightOnConfiguration(transport=httpx.MockTransport(handler))
    )


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


def test_ask_scopes_by_tags():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"results": [], "answer": ""})

    # tags accept Tag objects or bare ids, coerced to tag_id.
    make_client(handler).ask("q", tags=[Tag(id=3, name="legal"), 4])
    assert seen["body"] == {"query": "q", "tag_id": [3, 4]}
