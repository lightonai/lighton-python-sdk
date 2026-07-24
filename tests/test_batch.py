"""Batch ingestion: path validation, ignore_errors, sync result, async job/progress."""

import httpx
import pytest

from lighton import (
    BatchIngest,
    BatchIngestJob,
    ExecMode,
    LightOn,
    LightOnConfiguration,
    Workspace,
)


def _make_client(handler) -> LightOn:
    return LightOn(
        "k",
        config=LightOnConfiguration(
            transport=httpx.MockTransport(handler), max_requests_per_minute=None
        ),
    )


def _ws(handler) -> Workspace:
    ws = Workspace(id=42, name="w")
    ws._client = _make_client(handler)
    return ws


def _upload_handler(status_by_name=None):
    """Handler that answers uploads with the given per-filename ingestion status."""
    status_by_name = status_by_name or {}

    def handler(req: httpx.Request) -> httpx.Response:
        body = req.content
        for name, status in status_by_name.items():
            if name.encode() in body:
                return httpx.Response(
                    201,
                    json={
                        "id": abs(hash(name)) % 1000,
                        "filename": name,
                        "status": status,
                    },
                )
        return httpx.Response(201, json={"id": 1, "filename": "x", "status": "pending"})

    return handler


def test_missing_path_raises_before_upload(tmp_path):
    calls = {"n": 0}
    ws = _ws(
        lambda r: (
            calls.__setitem__("n", calls["n"] + 1),
            httpx.Response(201, json={"id": 1}),
        )[1]
    )
    missing = tmp_path / "nope.pdf"
    with pytest.raises(FileNotFoundError):
        ws.ingest_many([missing])
    assert calls["n"] == 0  # validated up front, no upload attempted


def test_missing_path_collected_when_ignore_errors(tmp_path):
    good = tmp_path / "good.pdf"
    good.write_bytes(b"%PDF fake")
    missing = tmp_path / "gone.pdf"

    result = _ws(_upload_handler()).ingest_many([good, missing], ignore_errors=True)
    assert isinstance(result, BatchIngest)
    assert len(result.succeeded) == 1
    assert len(result.failed) == 1
    assert result.failed[0].source == missing
    assert isinstance(result.failed[0].error, FileNotFoundError)


def test_sync_all_succeed(tmp_path):
    paths = []
    for n in ("a.pdf", "b.pdf", "c.pdf"):
        p = tmp_path / n
        p.write_bytes(b"%PDF fake")
        paths.append(p)

    result = _ws(_upload_handler()).ingest_many(paths)
    assert result.ok
    assert len(result.succeeded) == 3
    assert result.failed == []


def test_upload_error_raises_without_ignore(tmp_path):
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF fake")

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    # rate_limit_retries only retries 429; 5xx surfaces immediately
    ws = Workspace(id=42, name="w")
    ws._client = LightOn(
        "k",
        config=LightOnConfiguration(
            transport=httpx.MockTransport(handler), rate_limit_retries=0
        ),
    )
    with pytest.raises(Exception):
        ws.ingest_many([p])


def test_wait_splits_success_and_ingestion_failure(tmp_path):
    ok = tmp_path / "ok.pdf"
    ok.write_bytes(b"%PDF fake")
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF fake")

    # upload returns terminal statuses directly, so wait() resolves without polling
    handler = _upload_handler({"ok.pdf": "embedded", "bad.pdf": "fail"})
    result = _ws(handler).ingest_many([ok, bad], wait=True, ignore_errors=True)

    assert [f.filename for f in result.succeeded] == ["ok.pdf"]
    assert len(result.failed) == 1
    assert result.failed[0].source == bad


def test_glob_pattern_expands_to_files(tmp_path):
    for n in ("a.pdf", "b.pdf", "notes.txt"):
        (tmp_path / n).write_bytes(b"%PDF fake")

    result = _ws(_upload_handler()).ingest_many([str(tmp_path / "*.pdf")])
    assert len(result.succeeded) == 2  # the two .pdf, not the .txt
    assert result.ok


def test_glob_recursive_and_dedupe(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "top.pdf").write_bytes(b"%PDF fake")
    (tmp_path / "sub" / "deep.pdf").write_bytes(b"%PDF fake")

    # recursive glob + the same file listed explicitly → deduped to 3 uploads
    result = _ws(_upload_handler()).ingest_many(
        [str(tmp_path / "**" / "*.pdf"), tmp_path / "top.pdf"]
    )
    assert len(result.succeeded) == 2


def test_glob_matching_nothing_is_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        _ws(_upload_handler()).ingest_many([str(tmp_path / "*.pdf")])

    result = _ws(_upload_handler()).ingest_many(
        [str(tmp_path / "*.pdf")], ignore_errors=True
    )
    assert len(result.failed) == 1 and not result.succeeded


def test_async_returns_job_and_waits(tmp_path):
    paths = []
    for n in ("a.pdf", "b.pdf"):
        p = tmp_path / n
        p.write_bytes(b"%PDF fake")
        paths.append(p)

    job = _ws(_upload_handler()).ingest_many(paths, mode=ExecMode.ASYNC)
    assert isinstance(job, BatchIngestJob)
    result = job.wait(timeout=10)
    assert len(result.succeeded) == 2
    assert job.done
    prog = job.progress
    assert prog.total == 2 and prog.uploaded == 2 and prog.done
