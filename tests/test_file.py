"""Active-record File lifecycle, multipart upload, ingestion polling (mocked transport)."""

import httpx
import pytest

import json

from lighton import File, FileStatus, LightOn, LightOnConfiguration, Tag, Workspace


def _make_client(handler):
    return LightOn(
        "k", config=LightOnConfiguration(transport=httpx.MockTransport(handler))
    )


def test_create_uploads_multipart_and_absorbs_status(tmp_path):
    doc = tmp_path / "report.pdf"
    doc.write_bytes(b"%PDF-1.4 fake")
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent["ct"] = request.headers["content-type"]
        sent["body"] = request.content
        return httpx.Response(
            201, json={"id": 7, "filename": "report.pdf", "status": "pending"}
        )

    f = File(path=doc, workspace_id=3).create(_make_client(handler))
    assert f.id == 7
    assert f.status is FileStatus.pending  # coerced from the "pending" string
    assert f.status == "pending"  # ...but still compares equal (StrEnum)
    assert sent["ct"].startswith("multipart/form-data")
    assert b"report.pdf" in sent["body"] and b"%PDF-1.4 fake" in sent["body"]


def test_create_requires_path_and_workspace(tmp_path):
    client = _make_client(lambda r: httpx.Response(201, json={"id": 1}))
    with pytest.raises(ValueError):
        File(workspace_id=3).create(client)  # no path
    doc = tmp_path / "a.txt"
    doc.write_text("x")
    with pytest.raises(ValueError):
        File(path=doc).create(client)  # no workspace_id


def test_wait_polls_until_terminal(tmp_path):
    doc = tmp_path / "a.txt"
    doc.write_text("x")
    seq = iter(["parsing", "embedding", "embedded"])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, json={"id": 1, "status": "pending"})
        return httpx.Response(200, json={"id": 1, "status": next(seq)})

    f = File(path=doc, workspace_id=3).create(_make_client(handler))
    f.wait(timeout=5, poll=0)  # poll=0 → no real sleep
    assert f.status == "embedded"


def test_wait_raises_on_failure(tmp_path):
    from lighton.exceptions import LightOnError

    doc = tmp_path / "a.txt"
    doc.write_text("x")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, json={"id": 1, "status": "parsing"})
        return httpx.Response(
            200, json={"id": 1, "status": "fail", "status_detail": "bad pdf"}
        )

    f = File(path=doc, workspace_id=3).create(_make_client(handler))
    with pytest.raises(LightOnError, match="bad pdf"):
        f.wait(timeout=5, poll=0)


def test_tag_posts_ids_and_absorbs(tmp_path):
    doc = tmp_path / "a.txt"
    doc.write_text("x")
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/tags"):
            sent["path"] = request.url.path
            sent["body"] = json.loads(request.content)
            return httpx.Response(200, json={"id": 7, "status": "embedded"})
        return httpx.Response(201, json={"id": 7, "status": "pending"})

    f = File(path=doc, workspace_id=3).create(_make_client(handler))
    # accepts Tag objects and bare ids, coerced to a tag-id list
    f.tag([Tag(id=1, name="legal"), 2])
    assert sent["path"] == "/api/v3/files/7/tags"
    assert sent["body"] == {"tags": [1, 2]}
    assert f.status == "embedded"  # response absorbed onto self


def test_untag_deletes_each_tag(tmp_path):
    doc = tmp_path / "a.txt"
    doc.write_text("x")
    deleted = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            deleted.append(request.url.path)
            return httpx.Response(204)
        return httpx.Response(201, json={"id": 7, "status": "pending"})

    f = File(path=doc, workspace_id=3).create(_make_client(handler))
    f.untag([Tag(id=1, name="legal"), 2])
    assert deleted == ["/api/v3/files/7/tags/1", "/api/v3/files/7/tags/2"]


def test_tag_by_name_resolves_via_list(tmp_path):
    doc = tmp_path / "a.txt"
    doc.write_text("x")
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/v3/tags":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"id": 1, "name": "legal", "auto_assign": True},
                        {"id": 2, "name": "hr", "auto_assign": True},
                    ],
                    "next": None,
                },
            )
        if request.method == "POST" and request.url.path.endswith("/tags"):
            sent["body"] = json.loads(request.content)
            return httpx.Response(200, json={"id": 7, "status": "embedded"})
        return httpx.Response(201, json={"id": 7, "status": "pending"})

    f = File(path=doc, workspace_id=3).create(_make_client(handler))
    f.tag(["legal", 5])  # name resolved to id 1, bare id 5 passed through
    assert sent["body"] == {"tags": [5, 1]}


def test_tag_by_unknown_name_raises(tmp_path):
    doc = tmp_path / "a.txt"
    doc.write_text("x")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/v3/tags":
            return httpx.Response(200, json={"results": [], "next": None})
        return httpx.Response(201, json={"id": 7, "status": "pending"})

    f = File(path=doc, workspace_id=3).create(_make_client(handler))
    with pytest.raises(ValueError, match="unknown tag name"):
        f.tag(["nope"])


def test_tag_untag_empty_is_noop(tmp_path):
    doc = tmp_path / "a.txt"
    doc.write_text("x")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"  # only the create upload, no tag calls
        return httpx.Response(201, json={"id": 7, "status": "pending"})

    f = File(path=doc, workspace_id=3).create(_make_client(handler))
    assert f.tag([]) is f and f.untag([]) is f


def test_workspace_ingest_fills_workspace_id(tmp_path):
    doc = tmp_path / "a.txt"
    doc.write_text("x")
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent["body"] = request.content
        return httpx.Response(201, json={"id": 9, "status": "pending"})

    client = _make_client(handler)
    ws = Workspace(name="w")
    ws.id, ws._client = 42, client
    f = ws.ingest(File(path=doc))
    assert f.id == 9 and f.workspace_id == 42
    assert b'name="workspace_id"' in sent["body"] and b"42" in sent["body"]
