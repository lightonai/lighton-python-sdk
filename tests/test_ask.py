"""ask verb: request shaping (workspaces/files → ids, None-drop) and typed response."""

import json

import httpx
from pydantic import BaseModel

from lighton import LightOn, LightOnConfiguration, Tag, Workspace
from lighton.enums import RelevanceScoring


class Clause(BaseModel):
    """A sub-model, so the generated schema has a reference to inline."""

    text: str


def make_client(handler) -> LightOn:
    return LightOn(
        "k",
        config=LightOnConfiguration(
            transport=httpx.MockTransport(handler), max_requests_per_minute=None
        ),
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


def test_ask_relevance_scoring():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"results": [], "answer": ""})

    # relevance_scoring enum serializes to its string value in the body.
    make_client(handler).ask("q", relevance_scoring=RelevanceScoring.none)
    assert seen["body"] == {"query": "q", "relevance_scoring": "none"}


def test_ask_scopes_by_tags():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"results": [], "answer": ""})

    # tags accept Tag objects or bare ids, coerced to tag_id.
    make_client(handler).ask("q", tags=[Tag(id=3, name="legal"), 4])
    assert seen["body"] == {"query": "q", "tag_id": [3, 4]}


def test_ask_scopes_by_tag_names():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and req.url.path == "/api/v3/tags":
            return httpx.Response(
                200,
                json={
                    "results": [{"id": 3, "name": "legal", "auto_assign": True}],
                    "next": None,
                },
            )
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"results": [], "answer": ""})

    # names are resolved via Tag.list, mixed with a bare id
    make_client(handler).ask("q", tags=["legal", 4])
    assert seen["body"] == {"query": "q", "tag_id": [4, 3]}


def test_ask_structured_output_sends_response_format():
    seen = {}

    class Verdict(BaseModel):
        outcome: str
        clauses: list[Clause]

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"results": [], "answer": '{"outcome": "ok"}'})

    resp = make_client(handler).ask("did it pass?", schema=Verdict)
    fmt = seen["body"]["response_format"]
    # normalized like extract's: nested sub-model inlined, no $ref for the API to reject
    assert "$defs" not in fmt and "$ref" not in json.dumps(fmt)
    assert fmt["properties"]["clauses"]["items"]["properties"]["text"] == {
        "title": "Text",
        "type": "string",
    }
    # the answer is JSON *text*, the caller parses it
    assert json.loads(resp.answer) == {"outcome": "ok"}


def test_ask_without_schema_omits_response_format():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"results": [], "answer": ""})

    make_client(handler).ask("q")
    assert "response_format" not in seen["body"]
