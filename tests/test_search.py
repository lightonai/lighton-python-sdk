"""search verb: request shaping and typed response."""

import json

import httpx

from lighton import LightOn, LightOnConfiguration, SearchMode


def make_client(handler) -> LightOn:
    return LightOn(
        "k", config=LightOnConfiguration(transport=httpx.MockTransport(handler))
    )


def test_search_request_and_typed_response():
    def handler(req: httpx.Request) -> httpx.Response:
        assert json.loads(req.content) == {"query": "q", "mode": "vision"}
        return httpx.Response(200, json={"results": []})

    resp = make_client(handler).search("q", mode=SearchMode.vision)
    assert resp.results == []
