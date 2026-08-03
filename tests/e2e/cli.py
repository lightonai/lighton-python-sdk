#!/usr/bin/env python
"""End-to-end smoke test against the **live** LightOn API.

Not part of the pytest suite (which is offline): this hits the real API with
$LIGHTON_API_KEY, creates a throwaway workspace `e2e-<stamp>`, ingests the
documents in `tests/e2e/documents/`, exercises every SDK feature against them,
then deletes everything it created.

    uv run tests/e2e/cli.py                      # every step
    uv run tests/e2e/cli.py --only search --only ask
    uv run tests/e2e/cli.py --skip batch --keep  # leave the workspace behind
    uv run tests/e2e/cli.py --list-steps

Steps run in order and share one workspace; a failing step is reported and the
run continues, so one broken feature doesn't hide the rest. Exit code is 1 if
any step failed.
"""

from __future__ import annotations

import re
import time
import traceback
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import FunctionType

import typer
from pydantic import BaseModel, Field

from lighton import (
    ApiKey,
    ApiKeyScope,
    Attribute,
    ContentType,
    ExecMode,
    File,
    LightOn,
    RelevanceScoring,
    Role,
    SearchMode,
    Tag,
    Workspace,
    wait_all,
)

DOCS_DIR = Path(__file__).parent / "documents"
JOB_TIMEOUT = 300.0
PREREQS = ("workspace", "upload")  # implied by --only: the rest build on them


class DocumentSummary(BaseModel):
    """Doc-agnostic extraction schema (see --extract-schema in the module docs)."""

    title: str = Field(description="Document title.")
    summary: str = Field(description="One-sentence summary of the document.")
    language: str = Field(description="Primary language, as an ISO 639-1 code.")


@dataclass
class Ctx:
    client: LightOn
    docs: list[Path]
    stamp: str
    ask_query: str | None
    search_query: str | None
    ws: Workspace | None = None
    file: File | None = None
    tag: Tag | None = None
    topic: str | None = None  # derived once by _topic(), cached here
    cleanup: list[Callable[[], object]] = field(default_factory=list)

    def workspace(self) -> Workspace:
        """The shared workspace, or a clear error when the `workspace` step was skipped."""
        if self.ws is None:
            raise RuntimeError("this step needs the `workspace` step (don't skip it)")
        return self.ws

    def uploaded(self) -> File:
        """The ingested file, or a clear error when the `upload` step was skipped."""
        if self.file is None:
            raise RuntimeError("this step needs the `upload` step (don't skip it)")
        return self.file


STEPS: dict[str, Callable[[Ctx], None]] = {}


def step(fn: FunctionType) -> FunctionType:
    """Register a step under its own function name; order of definition is run order."""
    STEPS[fn.__name__] = fn
    return fn


def _say(msg: str, colour: str = typer.colors.WHITE) -> None:
    typer.secho(f"    {msg}", fg=colour)


def _topic(c: Ctx) -> str:
    """A phrase lifted from the first document, cached for the run.

    The run can't know what your corpus is about, and a query with no semantic
    overlap legitimately returns zero chunks — which would read as a broken
    search. Querying text the document actually contains keeps search/ask about
    the SDK's plumbing, not about retrieval quality. Override with --search-query.
    """
    if c.topic is None:
        page = c.client.parse(path=c.docs[0]).result.pages[0].markdown
        lines = (re.sub(r"[*#|>_`-]", " ", ln).strip() for ln in page.splitlines())
        longest = max(lines, key=lambda ln: len(ln.split()), default="")
        c.topic = " ".join(longest.split()[:12]) or c.docs[0].stem
        _say(f"derived query from {c.docs[0].name}: {c.topic!r}")
    return c.topic


# --- steps ------------------------------------------------------------------


@step
def workspace(c: Ctx) -> None:
    """create → list → get → save → refresh."""
    ws = Workspace(name=f"e2e-{c.stamp}", description="SDK e2e run").create(c.client)
    assert ws.id is not None, "create() returned no id"
    c.cleanup.append(ws.delete)
    c.ws = ws
    _say(f"created workspace {ws.id}")

    assert any(w.id == ws.id for w in Workspace.list(c.client)), "missing from list()"
    assert Workspace.get(c.client, ws.id).name == ws.name, "get() name mismatch"

    ws.description = "renamed by e2e"
    ws.save()
    ws.refresh()
    assert ws.description == "renamed by e2e", "save() did not persist"
    _say("list / get / save / refresh ok")


@step
def upload(c: Ctx) -> None:
    """ingest (blocking) → get_by_name → save title → list."""
    ws = c.workspace()
    doc = c.docs[0]
    f = ws.ingest(File(path=doc), wait=True)
    assert f.id is not None, "ingest() returned no id"
    c.file = f
    _say(f"ingested {doc.name} as file {f.id} ({f.status}, {f.total_pages} pages)")

    # By the name we uploaded, though the server stored it as f.filename.
    found = File.get_by_name(c.client, doc.name, workspace=ws)
    assert [x.id for x in found] == [f.id], f"get_by_name() returned {found}"

    f.title = f"e2e {doc.stem}"
    f.save()
    f.refresh()
    assert f.title == f"e2e {doc.stem}", "title did not persist"

    listed = File.list(c.client, workspace_id=ws.id)
    assert any(x.id == f.id for x in listed), "missing from File.list()"
    _say(f"get_by_name / save / list ok ({len(listed)} file(s) in workspace)")


@step
def tags(c: Ctx) -> None:
    """create → list → File.tag → File.untag."""
    f = c.uploaded()
    tag = Tag(name=f"e2e-{c.stamp}", description="SDK e2e run").create(c.client)
    assert tag.id is not None, "create() returned no id"
    c.cleanup.append(tag.delete)
    c.tag = tag
    _say(f"created tag {tag.id}")

    assert any(t.id == tag.id for t in Tag.list(c.client)), "missing from list()"
    f.tag([tag.name])  # by name → exercises resolve_ids' lookup path
    _say("tagged the file by name")
    f.untag([tag])
    f.tag([tag])  # re-tag: the search step filters on it
    _say("untag / re-tag ok")


@step
def content_types(c: Ctx) -> None:
    """list taxonomy → classify → set/clear attribute → facets → unclassify."""
    f = c.uploaded()
    roots = ContentType.list(c.client, include_attributes=True)
    if not roots:
        _say("no content types configured on this tenant, nothing to classify")
        return
    _say(f"{len(roots)} root content type(s): {', '.join(r.path for r in roots)}")

    ct = next(_leaves(roots))
    f.classify(ct)
    assert any(x.path == ct.path for x in f.facets()), "classify() did not stick"
    _say(f"classified as {ct.path}")

    attr = next((a for a in ct.attributes if _sample(a) is not None), None)
    if attr is None:
        _say("that content type defines no attributes, skipping set/clear")
    else:
        f.set_attribute(ct, attr.name, _sample(attr))
        values = {a.name: a.value for fc in f.facets() for a in fc.attributes}
        assert values.get(attr.name) is not None, f"{attr.name} was not set"
        _say(f"set attribute {attr.name}={values[attr.name]!r}")
        f.clear_attribute(ct, attr.name)

    f.unclassify(ct)
    assert not any(x.path == ct.path for x in f.facets()), "unclassify() did not stick"
    _say("unclassify ok")


def _leaves(nodes: list[ContentType]) -> Iterator[ContentType]:
    for n in nodes:
        yield from _leaves(n.children) if n.children else iter((n,))


def _sample(attr: Attribute) -> object:
    """A syntactically valid value for an attribute, or None if the type is unknown."""
    match attr.type:
        case "text":
            return "e2e"
        case "number":
            return 1
        case "boolean":
            return True
        case "date":
            return "2026-01-01"
        case "select" | "multi-select" if attr.choices:
            return attr.choices[0] if attr.type == "select" else [attr.choices[0]]
        case _:
            return None


@step
def search(c: Ctx) -> None:
    """workspace-scoped → file-scoped → tag-scoped."""
    ws, f = c.workspace(), c.uploaded()
    query = c.search_query or _topic(c)
    hits = c.client.search(
        query,
        workspaces=[ws],
        max_results=5,
        mode=SearchMode.text,
        relevance_scoring=RelevanceScoring.scoring_and_filtering,
        include_bboxes=True,
    ).results
    assert hits, f"workspace-scoped search for {query!r} returned nothing"
    _say(f"{len(hits)} chunk(s) in the workspace, top score {hits[0].score}")

    assert c.client.search(query, files=[f], max_results=3).results, (
        "file-scoped search returned nothing"
    )
    _say("file-scoped search ok")

    if c.tag is not None:
        got = c.client.search(query, tags=[c.tag], max_results=3).results
        _say(f"tag-scoped search returned {len(got)} chunk(s)")


@step
def ask(c: Ctx) -> None:
    """grounded answer over the workspace."""
    query = c.ask_query or f"What does the document say about {_topic(c)}?"
    r = c.client.ask(
        query,
        workspaces=[c.workspace()],
        max_results=5,
        relevance_scoring=RelevanceScoring.scoring_and_filtering,
    )
    assert r.answer, f"ask({query!r}) returned an empty answer"
    _say(f"answer ({len(r.results)} source chunk(s)): {r.answer[:160]}")


@step
def parse(c: Ctx) -> None:
    """sync parse → async parse job."""
    doc = c.docs[0]
    pages = c.client.parse(path=doc).result.pages
    assert pages, "sync parse returned no pages"
    _say(f"sync: {len(pages)} page(s), page 1 is {len(pages[0].markdown)} chars")

    job = c.client.parse(path=doc, mode=ExecMode.ASYNC, wait=True, timeout=JOB_TIMEOUT)
    assert job.result and job.result.pages, "async parse returned no pages"
    _say(f"async: job {job.id} completed in {job.processing_time_ms}ms")


@step
def extract(c: Ctx) -> None:
    """sync extract → async extract job (schema: DocumentSummary)."""
    doc = c.docs[0]
    r = c.client.extract(DocumentSummary, path=doc)
    assert r.result and r.result.data, "sync extract returned no data"
    _say(f"sync: {r.result.data}")

    job = c.client.extract(
        DocumentSummary, path=doc, mode=ExecMode.ASYNC, wait=True, timeout=JOB_TIMEOUT
    )
    assert job.result and job.result.data, "async extract returned no data"
    _say(f"async: job {job.id} completed in {job.processing_time_ms}ms")


@step
def batch(c: Ctx) -> None:
    """ingest_many SYNC (glob) → ASYNC job with live progress → wait_all."""
    ws = c.workspace()
    pattern = str(DOCS_DIR / "*")  # a glob string, expanded by ingest_many

    res = ws.ingest_many([pattern], mode=ExecMode.SYNC, ignore_errors=True)
    _say(f"sync: {len(res.succeeded)} uploaded, {len(res.failed)} failed")
    assert res.ok, f"sync batch failures: {[str(x.error) for x in res.failed]}"
    wait_all(res.succeeded)
    _say("wait_all: every upload reached a terminal-ok status")

    job = ws.ingest_many([pattern], mode=ExecMode.ASYNC, wait=True, ignore_errors=True)
    while not job.done:
        p = job.poll()
        _say(f"async: {p.uploaded}/{p.total} uploaded, {p.ingested} ingested")
        time.sleep(2.0)
    out = job.wait()
    assert out.ok, f"async batch failures: {[str(x.error) for x in out.failed]}"
    _say(f"async: {len(out.succeeded)} ingested")


@step
def keys(c: Ctx) -> None:
    """create (scoped) → list → get → save → delete."""
    ws = c.workspace()
    assert isinstance(ws.id, int)
    key = ApiKey(
        name=f"e2e-{c.stamp}",
        scopes=[ApiKeyScope(workspace_id=ws.id, role=Role.viewer)],
    ).create(c.client)
    assert key.id is not None, "create() returned no id"
    c.cleanup.append(key.delete)
    assert key.key is not None, "create() did not return the one-time secret"
    _say(f"created key {key.id} (prefix {key.prefix}, secret returned once)")

    assert any(k.id == key.id for k in ApiKey.list(c.client)), "missing from list()"
    assert ApiKey.get(c.client, key.id).key is None, "get() leaked the secret"

    key.name = f"e2e-{c.stamp}-renamed"
    key.save()
    key.refresh()
    assert key.name.endswith("-renamed"), "save() did not persist"
    _say("list / get / save ok")


# --- runner -----------------------------------------------------------------


def main(
    only: list[str] = typer.Option([], "--only", help="Run just these steps."),
    skip: list[str] = typer.Option([], "--skip", help="Skip these steps."),
    docs_dir: Path = typer.Option(
        DOCS_DIR, "--docs", help="Directory of documents to run against."
    ),
    ask_query: str = typer.Option(
        None,
        "--ask-query",
        help="Question for `ask` [default: built from the document].",
    ),
    search_query: str = typer.Option(
        None,
        "--search-query",
        help="Query for `search` [default: a phrase from the first document].",
    ),
    keep: bool = typer.Option(
        False, "--keep", help="Don't delete the workspace/tag/key afterwards."
    ),
    list_steps: bool = typer.Option(
        False, "--list-steps", help="Print steps and exit."
    ),
) -> None:
    """Run the LightOn SDK end-to-end against the live API."""
    if list_steps:
        for name, fn in STEPS.items():
            typer.echo(f"{name:15} {(fn.__doc__ or '').splitlines()[0]}")
        raise typer.Exit()

    unknown = (set(only) | set(skip)) - set(STEPS)
    if unknown:
        raise typer.BadParameter(f"unknown step(s): {', '.join(sorted(unknown))}")
    # --only pulls in the prerequisites: every other step needs a workspace with
    # an ingested file in it. --skip still wins, so they stay opt-out-able.
    wanted = (set(only) | set(PREREQS)) if only else set(STEPS)
    chosen = [n for n in STEPS if n in wanted and n not in skip]

    documents = sorted(
        p
        for p in docs_dir.glob("*")
        if p.is_file() and p.suffix and p.name != "README.md"
    )
    if not documents:
        typer.secho(
            f"no documents in {docs_dir} — drop a few files in there first "
            f"(see {docs_dir / 'README.md'})",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)
    typer.secho(
        f"{len(documents)} document(s): {', '.join(p.name for p in documents)}",
        fg=typer.colors.BLUE,
    )

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    failures: list[str] = []
    with LightOn() as client:  # reads LIGHTON_API_KEY
        c = Ctx(client, documents, stamp, ask_query, search_query)
        try:
            for name in chosen:
                typer.secho(f"\n▶ {name}", fg=typer.colors.CYAN, bold=True)
                started = time.monotonic()
                try:
                    STEPS[name](c)
                except Exception:
                    failures.append(name)
                    _say(traceback.format_exc().strip(), typer.colors.RED)
                    typer.secho(f"  ✗ {name}", fg=typer.colors.RED, bold=True)
                else:
                    took = time.monotonic() - started
                    typer.secho(f"  ✓ {name} ({took:.1f}s)", fg=typer.colors.GREEN)
        finally:
            _teardown(c, keep)

    typer.secho(
        f"\n{len(chosen) - len(failures)}/{len(chosen)} steps passed"
        + (f" — failed: {', '.join(failures)}" if failures else ""),
        fg=typer.colors.RED if failures else typer.colors.GREEN,
        bold=True,
    )
    raise typer.Exit(1 if failures else 0)


def _teardown(c: Ctx, keep: bool) -> None:
    """Delete what the run created (workspace delete takes its files with it)."""
    if keep:
        typer.secho(
            f"\n--keep: workspace {c.ws.id if c.ws else '?'} and its resources left behind",
            fg=typer.colors.YELLOW,
        )
        return
    typer.secho("\n▶ teardown", fg=typer.colors.CYAN, bold=True)
    for undo in reversed(c.cleanup):
        try:
            undo()
        except Exception as e:  # keep deleting the rest
            _say(f"cleanup failed: {e}", typer.colors.YELLOW)
    _say("deleted every resource this run created")


if __name__ == "__main__":
    typer.run(main)
