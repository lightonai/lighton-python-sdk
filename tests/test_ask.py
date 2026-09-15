"""ask verb: request shaping (workspaces/files → ids, None-drop) and typed response."""

import json

import httpx
import pytest
from pydantic import BaseModel

import lighton._client
from lighton import (
    ContentType,
    DoneEvent,
    LightOn,
    LightOnConfiguration,
    SourcesEvent,
    Tag,
    TokenEvent,
    Workspace,
)
from lighton.exceptions import LightOnAPIError, StreamError
from lighton.verbs.ask import _sse
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


def test_ask_facet_filters():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"results": [], "answer": ""})

    # content_type accepts ContentType objects or bare paths; attribute is a passthrough.
    make_client(handler).ask(
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


# --- streaming --------------------------------------------------------------

SSE = (
    b"event: sources\n"
    # A real `sources` payload, captured from the API and trimmed to the fields
    # AskResultItem requires (it is strict: UUID chunk_id, all four sub-scores).
    b'data: {"results": [{"chunk_id": "de58d140-2e1f-4295-82dc-d70ec699f7e3",'
    b' "content": "ctx", "score": 0.294,'
    b' "scores": {"text": 0.256, "vision": 0.231, "keyword": 0.24,'
    b' "multivector": 6.559, "relevance": 0.294},'
    b' "source": {"file_id": 863255, "filename": "a.pdf", "title": "a",'
    b' "mime_type": "pdf", "size_bytes": 21055, "page_start": 4, "page_end": 5,'
    b' "total_pages": 6, "tags": [], "content_types": [], "external_metadata": null},'
    b' "workspace": {"id": 7371, "name": "W"}}]}\n'
    b"\n"
    b": heartbeat\n"
    b"event: token\n"
    b'data: {"text": "Hel"}\n'
    b"\n"
    b"event: token\n"
    b'data: {"text": "lo"}\n'
    b"\n"
    b"event: done\n"
    b"data: {}\n"
    b"\n"
)


def _sse_client(body=SSE, status=200, seen=None):
    def handler(req: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen["body"] = json.loads(req.content)
        if status >= 400:
            return httpx.Response(status, json={"detail": "nope"})
        return httpx.Response(status, content=body)

    return make_client(handler)


def test_stream_yields_typed_events_in_order():
    seen = {}
    events = list(_sse_client(seen=seen).ask("q", stream=True))

    assert seen["body"]["stream"] is True
    assert [type(e) for e in events] == [
        SourcesEvent,
        TokenEvent,
        TokenEvent,
        DoneEvent,
    ]
    assert str(events[0].results[0].chunk_id).startswith("de58d140")
    assert events[0].results[0].source.filename == "a.pdf"  # same items ask returns
    assert "".join(e.text for e in events if isinstance(e, TokenEvent)) == "Hello"
    assert events[0].type == "sources"  # discriminator, for callers who prefer it


def test_stream_composes_with_structured_output():
    # response_format and stream are independent; tokens then spell out the JSON.
    class Outcome(BaseModel):
        outcome: str

    seen = {}
    body = (
        b"event: token\n" + b'data: {"text": "{\\"outcome\\":"}\n' + b"\n"
        b"event: token\n" + b'data: {"text": " \\"ok\\"}"}\n' + b"\n"
        b"event: done\ndata: {}\n\n"
    )
    chunks = [
        e.text
        for e in _sse_client(body, seen=seen).ask("q", schema=Outcome, stream=True)
        if isinstance(e, TokenEvent)
    ]

    assert seen["body"]["stream"] is True
    assert seen["body"]["response_format"]["type"] == "object"
    assert json.loads("".join(chunks)) == {"outcome": "ok"}


def test_stream_raises_on_an_error_event():
    # The answer is incomplete, so this must not read as a finished stream.
    body = (
        b'event: token\ndata: {"text": "partial"}\n\n'
        b'event: error\ndata: {"detail": "model unavailable"}\n\n'
    )
    stream = _sse_client(body).ask("q", stream=True)

    assert next(stream).text == "partial"  # whatever arrived first is still yielded
    with pytest.raises(StreamError, match="model unavailable") as excinfo:
        next(stream)
    assert excinfo.value.body == {"detail": "model unavailable"}
    assert not isinstance(excinfo.value, LightOnAPIError)  # HTTP was a clean 200


def test_stream_is_lazy_and_maps_http_errors_on_first_step():
    stream = _sse_client(status=422).ask("q", stream=True)  # no request yet
    with pytest.raises(LightOnAPIError) as excinfo:
        next(stream)
    assert excinfo.value.status_code == 422


def test_stream_still_retries_a_429(monkeypatch):
    monkeypatch.setattr(lighton._client.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"detail": "slow down"})
        return httpx.Response(200, content=SSE)

    client = LightOn(
        "k",
        config=LightOnConfiguration(
            transport=httpx.MockTransport(handler),
            max_requests_per_minute=None,
            rate_limit_retries=2,
        ),
    )
    assert len(list(client.ask("q", stream=True))) == 4
    assert calls["n"] == 2, "the cooldown retry must cover streaming too"


def test_stream_ignores_unknown_events_for_forward_compatibility():
    body = (
        b'event: token\ndata: {"text": "a"}\n\n'
        b'event: telemetry\ndata: {"whatever": 1}\n\n'
        b"event: done\ndata: {}\n\n"
    )
    events = list(_sse_client(body).ask("q", stream=True))
    assert [type(e) for e in events] == [TokenEvent, DoneEvent]


@pytest.mark.parametrize(
    "wire,expected",
    [
        # multi-line data accumulates, per the SSE spec
        (
            ["event: token", "data: line1", "data: line2", ""],
            [("token", "line1\nline2")],
        ),
        # a stream that ends without its trailing blank line still dispatches
        (["event: done", "data: {}"], [("done", "{}")]),
        # comments and unknown fields are skipped
        ([": ping", "id: 7", "event: token", "data: x", ""], [("token", "x")]),
        # no event field defaults to "message", as the spec says
        (["data: x", ""], [("message", "x")]),
        # a value with no leading space is kept verbatim
        (["event:token", "data:x", ""], [("token", "x")]),
    ],
)
def test_sse_parser_edge_cases(wire, expected):
    assert list(_sse(iter(wire))) == expected
