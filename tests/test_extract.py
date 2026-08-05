"""extract verb: pydantic/dict → vLLM schema, url vs path upload."""

import json

import httpx
import pytest
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel

from lighton import ExecMode, LightOn, LightOnConfiguration
from lighton.exceptions import LightOnError
from lighton.utils import (
    convert_pydantic_to_response_format_json,
    validate_response_format_json,
)

_DRAFT = "https://json-schema.org/draft/2020-12/schema"


def make_client(handler) -> LightOn:
    return LightOn(
        "k",
        config=LightOnConfiguration(
            transport=httpx.MockTransport(handler), max_requests_per_minute=None
        ),
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
    assert seen["body"]["schema"] == {"$schema": _DRAFT, **raw}
    assert seen["body"]["options"] == {"async": False}


def test_extract_dict_schema_refs_are_inlined():
    """A dict built from model_json_schema() carries $defs/$ref; the API rejects them."""

    class Address(BaseModel):
        city: str

    class Company(BaseModel):
        name: str
        addr: Address
        sites: list[Address] = []

    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=_OK)

    make_client(handler).extract(Company.model_json_schema(), url="https://x/i.pdf")
    schema = seen["body"]["schema"]
    assert "$defs" not in schema and "$ref" not in json.dumps(schema)
    city = {"city": {"title": "City", "type": "string"}}
    assert schema["properties"]["addr"]["properties"] == city
    assert schema["properties"]["sites"]["items"]["properties"] == city
    # same result as handing the model class over directly
    assert schema == convert_pydantic_to_response_format_json(Company)


def test_extract_dict_schema_with_dangling_ref_raises():
    client = make_client(lambda req: httpx.Response(200, json=_OK))
    raw = {"type": "object", "properties": {"addr": {"$ref": "#/$defs/Nope"}}}
    with pytest.raises(SchemaError, match="unresolved"):
        client.extract(raw, url="https://x/i.pdf")


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
    assert json.dumps({"$schema": _DRAFT, **raw}).encode() in seen["body"]
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


_DONE = {**_OK, "completed_at": "2026-01-01T00:00:01Z"}


def test_extract_async_wait_returns_finished_job():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.method == "POST"  # already terminal, no poll needed
        return httpx.Response(200, json=_DONE)

    job = make_client(handler).extract(
        {"type": "object"}, url="https://x/i.pdf", mode=ExecMode.ASYNC, wait=True
    )
    assert job.done and job.succeeded
    assert job.result is not None and job.result.data == [{"total": 42}]


def test_job_wait_polls_until_done():
    seq = iter([_OK, _OK, _DONE])  # not terminal until completed_at is set

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            return httpx.Response(202, json={"id": "e1", "status": "pending"})
        return httpx.Response(200, json=next(seq))

    job = make_client(handler).extract(
        {"type": "object"}, url="https://x/i.pdf", mode=ExecMode.ASYNC
    )
    assert job.wait(timeout=5, poll=0) is job and job.done  # poll=0 → no real sleep


def test_job_wait_raises_on_terminal_failure():
    failed = {"id": "e1", "status": "failed", "completed_at": "2026-01-01T00:00:01Z"}

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200 if req.method == "GET" else 202, json=failed)

    with pytest.raises(LightOnError, match="failed"):
        make_client(handler).extract(
            {"type": "object"}, url="https://x/i.pdf", mode=ExecMode.ASYNC, wait=True
        )


def test_extract_wait_requires_async_mode():
    client = make_client(lambda req: httpx.Response(200, json=_OK))
    with pytest.raises(ValueError, match="wait=True"):
        # wait without ASYNC is also a static error, hence the ignore
        client.extract({"type": "object"}, url="https://x/i.pdf", wait=True)  # ty: ignore[no-matching-overload]
