"""search verb: request shaping and typed response."""

import json

import httpx
import pytest

from lighton import (
    ContentType,
    FacetScope,
    LightOn,
    LightOnConfiguration,
    SearchMode,
    Tag,
)


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


def test_search_facet_filters():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"results": []})

    # content_type accepts ContentType objects or bare paths; attribute is a passthrough.
    make_client(handler).search(
        "q",
        content_type=[
            ContentType(path="legal:contract", code="contract", label="Contract"),
            "finance:*",
        ],
        attribute=["fiscal_year:2024|2025", "status:active"],
    )
    assert seen["body"] == {
        "query": "q",
        "content_type": ["legal:contract", "finance:*"],
        "attribute": ["fiscal_year:2024|2025", "status:active"],
    }


# --- scope= ----------------------------------------------------------------


def _scope_body():
    """A FacetScopeResponse with one scored content type and no completion."""
    return {
        "has_signal": True,
        "groups": [
            {
                "root": "patent",
                "root_label": "Patent",
                "max_score": 1.85,
                "content_types": [
                    {
                        "path": "patent:electricity",
                        "label": "Electricity",
                        "root": "patent",
                        "score": 1.85,
                        "chunk_count": 15,
                        "doc_count": 18000,
                        "attributes": [],
                    }
                ],
            }
        ],
        "prompt_context": "ctx",
    }


def test_search_scope_true_resolves_then_filters():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.url.path, json.loads(req.content)))
        if req.url.path == "/api/v3/content-types/scope":
            return httpx.Response(200, json=_scope_body())
        return httpx.Response(200, json={"results": []})

    make_client(handler).search("battery cooling", scope=True)

    assert [path for path, _ in seen] == [
        "/api/v3/content-types/scope",
        "/api/v3/search",
    ], "the scope must be resolved before the search it narrows"
    # resolved from the search's own query, with no model (no LLM call)
    assert seen[0][1] == {"query": "battery cooling"}
    assert seen[1][1] == {
        "query": "battery cooling",
        "content_type": ["patent:electricity"],
    }


def test_search_with_a_resolved_scope_sends_no_extra_request():
    seen = []
    scope = FacetScope.model_validate(
        {
            **_scope_body(),
            "scope_completion": {
                "content_type": "patent:electricity",
                "attribute": ["filing_date:>=2023-01-01"],
            },
        }
    )

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"results": []})

    make_client(handler).search("battery cooling", scope=scope)

    assert len(seen) == 1, "an already-resolved scope must not be resolved again"
    assert seen[0] == {
        "query": "battery cooling",
        "content_type": ["patent:electricity"],
        "attribute": ["filing_date:>=2023-01-01"],
    }


def test_search_scope_narrows_nothing_without_a_signal():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(json.loads(req.content))
        if req.url.path == "/api/v3/content-types/scope":
            return httpx.Response(200, json={**_scope_body(), "has_signal": False})
        return httpx.Response(200, json={"results": []})

    make_client(handler).search("q", scope=True)
    assert seen[1] == {"query": "q"}  # same body as a plain search


def test_search_refuses_a_scope_alongside_explicit_filters():
    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError(f"no request should be made, got {req.url}")

    client = make_client(handler)
    with pytest.raises(ValueError, match="not both"):
        client.search("q", scope=True, content_type=["legal"])
    with pytest.raises(ValueError, match="not both"):
        client.search("q", scope=True, attribute=["status:active"])
