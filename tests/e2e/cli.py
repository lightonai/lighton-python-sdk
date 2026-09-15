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
    AttributeType,
    ContentType,
    ExecMode,
    ExternalMetadata,
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
    """Doc-agnostic extraction schema, flat: no sub-models, so no `$defs`/`$ref`."""

    title: str = Field(description="Document title.")
    summary: str = Field(description="One-sentence summary of the document.")
    language: str = Field(description="Primary language, as an ISO 639-1 code.")


class Section(BaseModel):
    """A section heading; sub-model of `DocumentOutline`."""

    heading: str = Field(description="Section heading, verbatim as written.")
    page: int | None = Field(None, description="Page it starts on; null if unclear.")


class DocumentOutline(BaseModel):
    """Nested schema: `model_json_schema()` emits `$defs`/`$ref` for both sub-models.

    The API 422s on `$ref`, so this only reaches it because the SDK inlines them.
    Reuses `DocumentSummary` as a sub-model on purpose: the same model then appears
    both nested and standalone.
    """

    overview: DocumentSummary = Field(description="Summary of the whole document.")
    sections: list[Section] = Field(description="Every top-level section heading.")


class GroundedAnswer(BaseModel):
    """`ask(schema=...)` structured output: the LLM answer is constrained to this."""

    answer: str = Field(description="The answer, in one or two sentences.")
    confident: bool = Field(description="True if the sources fully support it.")


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
    content_type: ContentType | None = None  # the file stays classified as this
    other_content_type: ContentType | None = None  # a leaf it is NOT classified as
    attribute_filter: str | None = None  # an `attribute=` entry that should match
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
    f = ws.ingest(
        File(
            path=doc,
            external_metadata=ExternalMetadata(
                external_id=f"e2e-{c.stamp}",
                doc_type="incident",
                additional_metadata={"run": c.stamp},
            ),
        ),
        wait=True,
    )
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

    # external_metadata: set on upload, round-trips, and merges on update.
    assert f.external_metadata is not None, "external_metadata did not come back"
    assert f.external_metadata.external_id == f"e2e-{c.stamp}", "origin id was lost"
    f.save(external_metadata=ExternalMetadata(doc_type="ticket"))  # partial: merges
    f.refresh()
    got = f.external_metadata
    assert got is not None and got.doc_type == "ticket", "partial update did not apply"
    assert got.external_id == f"e2e-{c.stamp}", "a partial update dropped external_id"
    assert (got.additional_metadata or {}).get("run") == c.stamp, (
        "a partial update dropped additional_metadata"
    )
    _say(f"external metadata merged: {got.external_id} / {got.doc_type}")

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
    catalog = ContentType.templates(c.client)
    _say(
        f"{len(catalog)} template(s) available to adopt: {', '.join(t.path for t in catalog[:5])}"
    )

    roots = ContentType.list(c.client, include_attributes=True) or _seed_taxonomy(c)
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

    # Re-classify (mirrors the tags step's re-tag): facet_filters filters on this.
    f.classify(ct)
    c.content_type = ct
    c.other_content_type = next((x for x in _leaves(roots) if x.path != ct.path), None)
    if attr is not None:
        value = _sample(attr)
        f.set_attribute(ct, attr.name, value)
        # `name:value` for a plain string, else the type-agnostic "has any value" form.
        c.attribute_filter = (
            f"{attr.name}:{value}" if isinstance(value, str) else attr.name
        )
        _say(f"left attribute filter {c.attribute_filter!r} on the file")


def _seed_taxonomy(c: Ctx) -> list[ContentType]:
    """Build a throwaway tree so an empty tenant still exercises the facet paths.

    Exercises the taxonomy writes on the way: define a root, a child, a select and
    a text attribute, then a batch, with an undefine registered for teardown (it
    cascades the subtree, so one per root is enough).
    """
    code = f"e2e-{c.stamp}"  # codes are lowercase alphanumeric + hyphens, server-side
    for suffix in ("", "-other"):
        root = ContentType.define(
            c.client, code + suffix, f"E2E {c.stamp}{suffix}", description="SDK e2e run"
        )
        # undefine cascades, so the root takes its children and attributes with it.
        c.cleanup.append(lambda path=root.path: ContentType.undefine(c.client, path))

    child = ContentType.define(c.client, "child", "Child", parent=code)
    attr = ContentType.define_attribute(
        c.client, code, "e2e_marker", AttributeType.text
    )
    sel = ContentType.define_attribute(
        c.client, child, "e2e_region", AttributeType.select, choices=["FR", "US"]
    )
    assert sel.choices == ["FR", "US"], f"choices did not stick: {sel.choices}"
    try:
        ContentType.define_attribute(c.client, child, "nope", AttributeType.select)
    except ValueError:
        pass  # a select needs choices; refused client-side, no round trip
    else:
        raise AssertionError("a select without choices should have been refused")

    results = ContentType.batch(
        c.client,
        [
            {
                "action": "define_content_type",
                "parent_path": code,
                "code": "batched",
                "label": "Batched",
            },
            {
                "action": "define_attribute",
                "content_type_path": code,
                "name": "e2e_batched",
                "attribute_type": "boolean",
            },
        ],
    )
    assert all(r["status"] < 300 for r in results), f"batch failed: {results}"
    _say(
        f"defined {code} (+child, +batched), attributes {attr.name}/{sel.name}"
        f"/{results[1]['data']['name']}"
    )
    return ContentType.list(c.client, include_attributes=True)


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
def facet_filters(c: Ctx) -> None:
    """content_type= / attribute= on search and ask (needs the content_types step)."""
    ws = c.workspace()
    ct = c.content_type
    if ct is None:
        _say("nothing classified — run with --only content_types --only facet_filters")
        return
    query = c.search_query or _topic(c)

    # ContentType object, not just a path: the SDK coerces it via `.path`.
    hits = c.client.search(
        query, workspaces=[ws], content_type=[ct], max_results=5
    ).results
    assert hits, (
        f"content_type={ct.path!r} returned nothing, but the file is classified as it"
    )
    _say(f"search content_type={ct.path!r} → {len(hits)} chunk(s)")

    # A leaf the file is NOT classified as must filter it out, otherwise the
    # filter never reached the server.
    if c.other_content_type is not None:
        other = c.other_content_type.path
        assert not c.client.search(
            query, workspaces=[ws], content_type=[other], max_results=5
        ).results, f"content_type={other!r} still returned chunks — filter ignored?"
        _say(f"search content_type={other!r} → 0 chunk(s), as expected")

    if c.attribute_filter:
        got = c.client.search(
            query, workspaces=[ws], attribute=[c.attribute_filter], max_results=5
        ).results
        assert got, f"attribute={c.attribute_filter!r} returned nothing"
        _say(f"search attribute={c.attribute_filter!r} → {len(got)} chunk(s)")

        miss = f"{c.attribute_filter.split(':')[0]}:e2e-no-such-value"
        assert not c.client.search(
            query, workspaces=[ws], attribute=[miss], max_results=5
        ).results, f"attribute={miss!r} still returned chunks — filter ignored?"
        _say(f"search attribute={miss!r} → 0 chunk(s), as expected")

    r = c.client.ask(
        query,
        workspaces=[ws],
        content_type=[ct.path],
        attribute=[c.attribute_filter] if c.attribute_filter else None,
        max_results=5,
    )
    assert r.results, "ask with facet filters grounded on nothing"
    _say(f"ask with facet filters → {len(r.results)} source chunk(s)")


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
    """grounded answer over the workspace → structured answer via schema=."""
    query = c.ask_query or f"What does the document say about {_topic(c)}?"
    r = c.client.ask(
        query,
        workspaces=[c.workspace()],
        max_results=5,
        relevance_scoring=RelevanceScoring.scoring_and_filtering,
    )
    assert r.answer, f"ask({query!r}) returned an empty answer"
    _say(f"answer ({len(r.results)} source chunk(s)): {r.answer[:160]}")

    # structured output: the answer comes back as JSON text matching the schema.
    s = c.client.ask(query, workspaces=[c.workspace()], schema=GroundedAnswer)
    parsed = GroundedAnswer.model_validate_json(s.answer)  # raises if off-schema
    _say(f"structured: confident={parsed.confident} {parsed.answer[:120]}")


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
    """sync → async job → nested schema (model + raw dict) → an ingested file=."""
    doc = c.docs[0]
    r = c.client.extract(DocumentSummary, path=doc)
    assert r.result and r.result.data, "sync extract returned no data"
    _say(f"sync: {r.result.data}")

    job = c.client.extract(
        DocumentSummary, path=doc, mode=ExecMode.ASYNC, wait=True, timeout=JOB_TIMEOUT
    )
    assert job.result and job.result.data, "async extract returned no data"
    _say(f"async: job {job.id} completed in {job.processing_time_ms}ms")

    # A 422 on either call means $ref reached the API: the SDK stopped inlining.
    nested = c.client.extract(DocumentOutline, path=doc)
    assert nested.result and nested.result.data, "nested extract returned no data"
    _say(f"nested (model class): {nested.result.data}")

    raw = DocumentOutline.model_json_schema()  # carries $defs/$ref verbatim
    assert "$defs" in raw, "pydantic stopped emitting $defs, this case is now moot"
    as_dict = c.client.extract(raw, path=doc)
    assert as_dict.result and as_dict.result.data, (
        "nested dict extract returned no data"
    )
    _say(f"nested (raw dict): {as_dict.result.data}")

    # file=: extract from the already-ingested file, no re-upload
    by_id = c.client.extract(DocumentSummary, file=c.uploaded())
    assert by_id.result and by_id.result.data, "extract by file_id returned no data"
    _say(f"by file_id {c.uploaded().id}: {by_id.result.data}")


@step
def replace(c: Ctx) -> None:
    """replace the file content in place: same id, tags and classifications survive."""
    f = c.uploaded()
    before = (f.id, f.title, f.total_pages, f.size)
    # `tags` isn't a File model field (the response shape would clash on _absorb),
    # so read them off the raw payload.
    tags_before = _tag_ids(c, f)
    facets_before = {x.path for x in f.facets()}

    # A document whose byte size differs, so "the content changed" is checkable.
    new = next((d for d in c.docs[1:] if d.stat().st_size != f.size), None)
    if new is None:
        _say("no second document of a different size, nothing to replace with")
        return

    # The PATCH lands a queued reprocess next to the previous run's status: the
    # exact window where a naive wait() would report success for unstarted work.
    f.replace(new)
    assert f.pending_reprocess == "update", (
        f"expected a queued reprocess, got {f.pending_reprocess!r}"
    )
    _say(
        f"queued: pending_reprocess={f.pending_reprocess!r} beside stale status={f.status!r}"
    )

    f.wait()
    assert f.pending_reprocess is None, "wait() returned with a reprocess still queued"
    f.refresh()
    _say(
        f"replaced with {new.name}: {before[2]} pages/{before[3]}B → {f.total_pages} pages/{f.size}B"
    )

    _say(f"filename now {f.filename!r}, title still {f.title!r}")
    assert f.id == before[0], "the id changed, that is the whole point of replace()"
    assert f.title == before[1], "title should survive, it is the user-facing name"
    assert f.filename == new.name, (
        f"filename should follow the new file, got {f.filename!r}"
    )
    assert (f.total_pages, f.size) != before[2:], "content did not change"
    assert f.status in ("embedded", "parsed"), f"re-ingestion ended {f.status}"

    assert _tag_ids(c, f) == tags_before, "tags did not survive the replace"
    assert {x.path for x in f.facets()} == facets_before, (
        "classifications did not survive the replace"
    )
    _say(
        f"survived: tags {tags_before or '(none)'}, facets {facets_before or '(none)'}"
    )


def _tag_ids(c: Ctx, f: File) -> set[int]:
    """The file's tag ids, straight off the API payload (File models no `tags` field)."""
    data = c.client._request("GET", f"/api/v3/files/{f.id}")
    return {t["id"] if isinstance(t, dict) else t for t in data.get("tags", [])}


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

    # Tear the corpus down in one request instead of one DELETE per file.
    doomed = File.list(c.client, workspace_id=ws.id)
    keep = c.uploaded().id  # the shared file, later steps still need it
    doomed = [f for f in doomed if f.id != keep]
    File.delete_many(c.client, doomed)
    left = {f.id for f in File.list(c.client, workspace_id=ws.id)}
    assert left == {keep}, f"bulk delete left {left - {keep}} behind"
    _say(f"bulk-deleted {len(doomed)} file(s) in one request, {len(left)} left")


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
