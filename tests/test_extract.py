"""extract verb: pydantic → vLLM schema, raw-dict passthrough, url vs path upload."""

import json

import httpx
import pytest
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel

from lighton import ExecMode, LightOn, LightOnConfiguration
from lighton.utils import validate_response_format_json


def make_client(handler) -> LightOn:
    return LightOn(
        "k", config=LightOnConfiguration(transport=httpx.MockTransport(handler))
    )


_OK = {"id": "e1", "status": "completed", "result": {"data": [{"total": 42}]}}


def test_extract_pydantic_schema_is_normalized():
    seen = {}

    class Person(BaseModel):
        nom: str
        prenom: str | None = None

    class Doc(BaseModel):
        personnes: list[Person]
        objet: str | None = None

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=_OK)

    resp = make_client(handler).extract(Doc, url="https://x/i.pdf")
    assert resp.result is not None
    assert resp.result.data == [{"total": 42}]

    schema = seen["body"]["schema"]
    dumped = json.dumps(schema)
    # the converted schema is itself a valid JSON Schema (raises otherwise)
    validate_response_format_json(schema)
    # draft marker added, nested model inlined (no $defs/$ref left)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert "$defs" not in schema and "$ref" not in dumped
    # nested Person is inlined under personnes.items
    person = schema["properties"]["personnes"]["items"]
    assert person["properties"]["nom"] == {"type": "string", "title": "Nom"}
    # nullable str | None collapses to a type array
    assert person["properties"]["prenom"]["type"] == ["string", "null"]
    assert schema["properties"]["objet"]["type"] == ["string", "null"]


def test_extract_url_sends_json():
    seen = {}
    raw = {"type": "object", "properties": {"total": {"type": "number"}}}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=_OK)

    make_client(handler).extract(raw, url="https://x/i.pdf", options={"async": False})
    assert seen["body"]["document"] == "https://x/i.pdf"
    assert seen["body"]["schema"] == raw  # dict passed through untouched
    assert seen["body"]["options"] == {"async": False}


def test_extract_path_sends_multipart(tmp_path):
    raw = {"type": "object", "properties": {"total": {"type": "number"}}}
    f = tmp_path / "doc.png"
    f.write_bytes(b"\x89PNG")
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["ctype"] = req.headers.get("content-type", "")
        seen["body"] = req.content
        return httpx.Response(200, json=_OK)

    make_client(handler).extract(raw, path=f, options={"async": False})
    assert seen["ctype"].startswith("multipart/form-data")
    # file part + schema/options as JSON-encoded form fields
    assert b'name="file"' in seen["body"] and b"doc.png" in seen["body"]
    assert json.dumps(raw).encode() in seen["body"]
    assert b'{"async": false}' in seen["body"]


def test_extract_requires_exactly_one_source():
    client = make_client(lambda req: httpx.Response(200, json=_OK))
    raw = {"type": "object"}
    with pytest.raises(ValueError):
        client.extract(raw)
    with pytest.raises(ValueError):
        client.extract(raw, path="d.png", url="https://x/i.pdf")


def test_extract_async_returns_job_and_polls_in_place():
    seen = {}
    raw = {"type": "object"}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            seen["body"] = json.loads(req.content)
            return httpx.Response(202, json={"id": "extract_Kg", "status": "pending"})
        assert req.url.path == "/api/v3/extract/extract_Kg"  # GET poll
        assert req.url.params.get("page") == "2"
        return httpx.Response(200, json=_OK)

    job = make_client(handler).extract(raw, url="https://x/i.pdf", mode=ExecMode.ASYNC)
    assert job.id == "extract_Kg" and not job.succeeded
    assert seen["body"]["options"] == {"async": True}

    same = job.poll(page=2)  # updates in place, returns self
    assert same is job and job.succeeded
    assert job.result is not None and job.result.data == [{"total": 42}]


def test_extract_malformed_dict_schema_raises():
    client = make_client(lambda req: httpx.Response(200, json=_OK))
    # "type" must be a string/array, not an int — invalid per the meta-schema
    with pytest.raises(SchemaError):
        client.extract({"type": 123}, url="https://x/i.pdf")
