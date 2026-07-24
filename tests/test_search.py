"""search verb: request shaping and typed response."""

import json

import httpx

from lighton import LightOn, LightOnConfiguration, SearchMode, Tag


def make_client(handler) -> LightOn:
    return LightOn(
        "k",
        config=LightOnConfiguration(
            transport=httpx.MockTransport(handler), max_requests_per_minute=None
        ),
    )


def test_search_request_and_typed_response():
    def handler(req: httpx.Request) -> httpx.Response:
        assert json.loads(req.content) == {"query": "q", "mode": "vision"}
        return httpx.Response(200, json={"results": []})

    resp = make_client(handler).search("q", mode=SearchMode.vision)
    assert resp.results == []


def test_search_scopes_by_tags():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"results": []})

    # tags accept Tag objects or bare ids, coerced to tag_id.
    make_client(handler).search("q", tags=[Tag(id=3, name="legal"), 4])
    assert seen["body"] == {"query": "q", "tag_id": [3, 4]}


def test_search_scopes_by_tag_names():
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
        return httpx.Response(200, json={"results": []})

    make_client(handler).search("q", tags=["legal", 4])
    assert seen["body"] == {"query": "q", "tag_id": [4, 3]}
