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
    ContentTypeAction,
    DoneEvent,
    DownloadPurpose,
    ExecMode,
    ExternalMetadata,
    FacetAction,
    FacetScope,
    File,
    LightOn,
    MAX_CONTENT_TYPE_ACTIONS,
    MAX_FACET_ACTIONS,
    RelevanceScoring,
    Role,
    SearchMode,
    SourcesEvent,
    Tag,
    TokenEvent,
    ThumbnailStatus,
    Workspace,
    wait_all,
)
from lighton.exceptions import LightOnAPIError, NotFoundError

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
    scope_model: str | None = None  # names the LLM the `scope` step infers with
    ws: Workspace | None = None
    file: File | None = None
    tag: Tag | None = None
    content_type: ContentType | None = None  # the file stays classified as this
    other_content_type: ContentType | None = None  # a leaf it is NOT classified as
    attribute_filter: str | None = None  # an `attribute=` entry that should match
    seeded_roots: list[str] = field(default_factory=list)  # roots _seed_taxonomy made
    resolved_scope: FacetScope | None = None  # what the `scope` step resolved
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

    listed = next(w for w in Workspace.list(c.client) if w.id == ws.id)
    assert listed.user_role is not None, "user_role is a free read off the listing"
    _say(
        f"user_role={listed.user_role}, sync={listed.sync and listed.sync.datasource_type}"
    )

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

    # Classification coverage shows up on the workspace listing, not on get().
    f.classify(ct)
    listed = next(w for w in Workspace.list(c.client) if w.id == c.workspace().id)
    tax = listed.taxonomy
    assert tax is not None, "taxonomy is None despite a classified file"
    assert tax.classified_files_rate > 0, f"rate is {tax.classified_files_rate}"
    assert any(r.path == ct.path.split(":")[0] for r in tax.root_content_types), (
        f"{ct.path} missing from {[r.path for r in tax.root_content_types]}"
    )
    _say(
        f"taxonomy: {tax.classified_files_rate:.0%} classified, roots "
        f"{[(r.path, r.count) for r in tax.root_content_types]}"
    )
    before = listed.taxonomy
    listed.refresh()  # detail endpoint omits the key, so it must survive
    assert listed.taxonomy == before, "refresh() cleared a field it never receives"
    _say("taxonomy survives refresh()")

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
    # The labels and descriptions carry real meaning on purpose: `scope()` *ranks
    # the taxonomy against a question*, so a tree labelled "E2E <stamp>" gives the
    # scorer nothing to rank and every scope assertion would be flaky — on exactly
    # the empty tenants that need seeding. The two roots are deliberately about
    # different subjects, which is what makes `other_content_type` a real negative.
    # Codes stay stamped: teardown keys on them, and undefine cascades, so it must
    # only ever reach a root this run created.
    for suffix, label, about in (
        (
            "",
            "Technical Documentation",
            "Maintenance manuals, technical orders, service bulletins and "
            "incident reports.",
        ),
        (
            "-other",
            "Financial Statements",
            "Invoices, balance sheets, quarterly earnings and audit reports.",
        ),
    ):
        root = ContentType.define(c.client, code + suffix, label, description=about)
        # undefine cascades, so the root takes its children and attributes with it.
        c.cleanup.append(lambda path=root.path: ContentType.undefine(c.client, path))
        c.seeded_roots.append(root.path)

    child = ContentType.define(
        c.client,
        "child",
        "Incident Reports",
        parent=code,
        description="Fault and incident reports filed against equipment.",
    )
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
            ContentTypeAction.define(
                "batched",
                "Service Bulletins",
                parent=code,
                description="Manufacturer service bulletins and airworthiness "
                "directives.",
            ),
            # a raw dict stays a valid entry, the escape hatch both batches share
            {
                "action": "define_attribute",
                "content_type_path": code,
                "name": "e2e_batched",
                "attribute_type": "boolean",
            },
        ],
    )
    assert all(r.status < 300 for r in results), f"batch failed: {results}"
    assert results[1].data is not None, "define_attribute returns the definition"
    _say(
        f"defined {code} (+child, +batched), attributes {attr.name}/{sel.name}"
        f"/{results[1].data['name']}"
    )

    try:
        ContentType.batch(c.client, [ContentTypeAction.undefine("nope:not-a-type")])
    except LightOnAPIError as e:
        assert e.index == 0, f"the failing action's position should be 0, got {e.index}"
    else:
        raise AssertionError("an unknown content type should have failed the batch")

    assert not ContentType.batch(c.client, []), "an empty batch should not have hit API"
    with_too_many = [ContentTypeAction.undefine(code)] * (MAX_CONTENT_TYPE_ACTIONS + 1)
    try:
        ContentType.batch(c.client, with_too_many)
    except ValueError:
        pass  # refused client-side, no round trip
    else:
        raise AssertionError("past the cap the batch should have been refused")
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
def facet_batch(c: Ctx) -> None:
    """facets/batch: many writes in one request, the fail-fast index, the 50 cap."""
    f = c.uploaded()
    ct = c.content_type
    if ct is None:
        _say("nothing classified, run with --only content_types --only facet_batch")
        return

    # Only `ct`: classifying a sibling from the same tree is a 400 by design.
    actions: list[FacetAction | dict[str, object]] = [FacetAction.classify(ct)]
    attr = next((a for a in ct.attributes if _sample(a) is not None), None)
    if attr is not None:
        actions += [
            FacetAction.set_attribute(ct, attr.name, _sample(attr)),
            FacetAction.clear_attribute(ct, attr.name),
            # restore: facet_filters (the next step) filters on this value
            FacetAction.set_attribute(ct, attr.name, _sample(attr)),
        ]

    results = f.batch_facets(actions)
    assert len(results) == len(actions), (
        f"{len(results)} result(s) for {len(actions)} action(s)"
    )
    assert all(r.status < 300 for r in results), (
        f"batch reported {[r.status for r in results]}"
    )
    _say(f"{len(actions)} action(s) in one request → {[r.status for r in results]}")

    # A domain error fails fast and names the offender; what came before it sticks.
    try:
        f.batch_facets(
            [FacetAction.classify(ct), FacetAction.classify(f"no-such-{c.stamp}")]
        )
    except LightOnAPIError as e:
        assert e.index == 1, f"expected index 1, got {e.index}"
        _say(f"fail-fast reported index {e.index}")
    else:
        raise AssertionError("an unknown content type should have failed the batch")

    assert any(x.path == ct.path for x in f.facets()), (
        "the committed prefix did not stick"
    )

    assert not f.batch_facets([]), "an empty batch should not have hit the API"

    try:
        f.batch_facets([FacetAction.classify(ct)] * (MAX_FACET_ACTIONS + 1))
    except ValueError:
        _say(f"over {MAX_FACET_ACTIONS} actions: refused client-side, no round trip")
    else:
        raise AssertionError(f"{MAX_FACET_ACTIONS + 1} actions should be refused")


@step
def scope(c: Ctx) -> None:
    """content-types/scope: the three modes, the wire shapes, the knobs.

    Scores whatever taxonomy the account already has; run it after the
    `content_types` step if you want something guaranteed to be there. The offline
    suite already pins the client side (what gets sent, what `scope=` means), so
    everything here is a *server* contract: shapes the curated models bet on, and
    knobs only the live endpoint can honour.
    """
    query = c.search_query or _topic(c)

    # Prompt mode: no model, so no completion, just the prompt to run yourself.
    resolved = ContentType.scope(c.client, query)
    c.resolved_scope = resolved
    hits = resolved.content_types
    _say(
        f"scope({query!r}) → has_signal={resolved.has_signal}, "
        f"{len(hits)} content type(s)"
    )
    assert resolved.completion is None, (
        "no model= was passed, so there is no completion"
    )
    if not hits:
        _say(
            "nothing scored — run with --only content_types --only scope",
            typer.colors.YELLOW,
        )
        return
    # prompt_context describes the types that scored, so it's only guaranteed once
    # something did — an empty taxonomy is a skipped step, not a bug.
    assert resolved.prompt_context, "prompt mode must return a prompt_context"
    for hit in hits[:3]:
        _say(f"  {hit.score:.2f}  {hit.path}  ({hit.doc_count} doc(s))")

    # prompt_version identifies the prompt that was built, as a `t:<template>.d:<data>`
    # pair. Deliberately *not* asserted stable across two identical calls: the
    # docstring's claim is one-directional ("same value means the same prompt was
    # built"), not the converse. The `d:` half hashes the taxonomy behind the
    # prompt, which moves on a live tenant between two requests — doc counts shift,
    # retrieval reorders — so equality here would be a flake, not a contract.
    assert resolved.prompt_version, "prompt mode must return a prompt_version"
    _say(f"prompt_version: {resolved.prompt_version}")

    _assert_attribute_shapes(c, resolved)
    _assert_group_coherence(resolved)

    # --- the knobs, which only the live endpoint can honour -------------------
    if len(hits) > 1:
        capped = ContentType.scope(c.client, query, max_results=1)
        assert len(capped.content_types) <= 1, (
            f"max_results=1 returned {len(capped.content_types)} content type(s)"
        )
        _say(f"max_results=1 → {len(capped.content_types)} hit (from {len(hits)})")

    # threshold gates has_signal, and 0 disables the gate outright. `_compact`
    # drops None and not falsiness, so the 0 really does reach the server.
    opened = ContentType.scope(c.client, query, threshold=0)
    assert opened.has_signal, "threshold=0 disables the gate, has_signal stayed False"
    shut = ContentType.scope(c.client, query, threshold=1e9)
    assert not shut.has_signal, "nothing scores above 1e9, has_signal should be False"
    _say("threshold: 0 → has_signal, 1e9 → no signal")

    # Catalog mode: skip scoring entirely, and ignore max_results/threshold while
    # doing it. Distinct from the no-query form below, which still scores.
    catalog = ContentType.scope(
        c.client, query, relevance_scoring=RelevanceScoring.none, max_results=1
    )
    assert catalog.content_types, "catalog mode returned no content types"
    assert all(ct.score == 0 for ct in catalog.content_types), (
        f"catalog mode should score 0: {[ct.score for ct in catalog.content_types[:5]]}"
    )
    if len(hits) > 1:
        assert len(catalog.content_types) > 1, (
            "catalog mode should ignore max_results, but it capped at 1"
        )
    _say(f"relevance_scoring=none → {len(catalog.content_types)} type(s), all score 0")

    # No query at all: the full schema, what you bake into a system prompt.
    everything = ContentType.scope(c.client)
    assert everything.content_types, "the no-query catalog came back empty"
    assert everything.prompt_context, "the no-query catalog carries no prompt_context"
    _say(f"scope() with no query → {len(everything.content_types)} content type(s)")

    # The file is classified under c.content_type, so if that type scored at all
    # the server must count it. Conditional on scoring: a swapped --docs corpus
    # legitimately may not surface it, and that is not an SDK failure.
    ct = c.content_type
    if ct is not None:
        scored = next((h for h in hits if h.path == ct.path), None)
        if scored is None:
            _say(f"{ct.path} did not score for this query", typer.colors.YELLOW)
        else:
            assert scored.doc_count >= 1, (
                f"{ct.path} has a classified file but reports {scored.doc_count} doc(s)"
            )
            _say(f"{ct.path} scored {scored.score:.2f}, {scored.doc_count} doc(s)")


def _assert_attribute_shapes(c: Ctx, resolved: FacetScope) -> None:
    """The bet the curated models make: hits carry real `Attribute` definitions.

    The OpenAPI schema types `ScoredContentType.attributes` as free-form `object[]`,
    which is why `ScopedContentType` is curated to reuse `Attribute` instead of
    being generated. `extra="ignore"` means a wire drift lands as *blank* Attributes
    rather than an error, so only asserting on the contents can catch it.
    """
    attrs = [(hit.path, a) for hit in resolved.content_types for a in hit.attributes]
    if not attrs:
        _say("no scored type carries attributes, shapes unchecked", typer.colors.YELLOW)
        return

    for path, a in attrs:
        assert a.name, f"{path} returned an attribute with no name"
        assert a.type is not None, f"{path}.{a.name} came back with no type"
        # Definitions, not a file's values: `value` is always None on a scope hit.
        assert a.value is None, f"{path}.{a.name} carries a value ({a.value!r})"
    _say(f"{len(attrs)} attribute definition(s), all named, typed and unvalued")

    # The seeded select pins `choices` exactly. On a tenant we didn't seed there's
    # no attribute we know the answer for, so the loop above is all there is.
    if not c.seeded_roots:
        _say(
            "tenant has its own taxonomy, so nothing was seeded: `choices` unchecked",
            typer.colors.YELLOW,
        )
        return
    sel = next((a for _, a in attrs if a.name == "e2e_region"), None)
    if sel is None:
        _say("the seeded select did not score, choices unchecked", typer.colors.YELLOW)
        return
    assert sel.choices == ["FR", "US"], f"choices came back as {sel.choices!r}"
    _say(f"seeded select e2e_region kept its choices: {sel.choices}")


def _assert_group_coherence(resolved: FacetScope) -> None:
    """`content_types` is the flattened `groups`, best score first."""
    flat = [ct for group in resolved.groups for ct in group.content_types]
    assert sorted(ct.path for ct in flat) == sorted(
        ct.path for ct in resolved.content_types
    ), "content_types is not the flattening of groups"

    scores = [ct.score for ct in resolved.content_types]
    assert scores == sorted(scores, reverse=True), f"hits are not best-first: {scores}"

    for group in resolved.groups:
        if not group.content_types:
            continue
        best = max(ct.score for ct in group.content_types)
        assert abs(group.max_score - best) < 1e-6, (
            f"{group.root}: max_score {group.max_score}, best member {best}"
        )
        stray = [ct.path for ct in group.content_types if ct.root != group.root]
        assert not stray, f"{group.root} holds hits rooted elsewhere: {stray}"
    _say(f"{len(resolved.groups)} group(s) coherent with the flattened hits")


@step
def scope_filters(c: Ctx) -> None:
    """scope= on search and ask: apply it, then the refusals (needs the `scope` step)."""
    ws = c.workspace()
    query = c.search_query or _topic(c)
    resolved = c.resolved_scope
    if resolved is None or not resolved.content_types:
        _say(
            "no scope resolved — run with --only content_types --only scope "
            "--only scope_filters",
            typer.colors.YELLOW,
        )
        return

    # A scored hit is a ContentTypeRef: it filters without unwrapping .path.
    best = resolved.content_types[0]
    got = c.client.search(
        query, workspaces=[ws], content_type=[best], max_results=5
    ).results
    _say(f"search(content_type=[<hit {best.path}>]) → {len(got)} chunk(s)")

    # scope=True: resolve from this very query, then narrow by what it scored.
    hits = c.client.search(query, workspaces=[ws], scope=True, max_results=5).results
    _say(f"search(scope=True) → {len(hits)} chunk(s)")

    # A scope resolved up front is applied as-is, with no second resolution.
    same = c.client.search(
        query, workspaces=[ws], scope=resolved, max_results=5
    ).results
    _say(f"search(scope=<pre-resolved>) → {len(same)} chunk(s)")

    # ask takes the same scope=, through the same resolve_scope().
    answered = c.client.ask(query, workspaces=[ws], scope=True, max_results=5)
    assert answered.answer, "ask(scope=True) returned an empty answer"
    _say(f"ask(scope=True) → {len(answered.results)} source(s): {answered.answer[:80]}")

    # scope= replaces the explicit filters, it never merges with them. Spelled out
    # twice rather than looped: a **kwargs splat doesn't type-check against search.
    try:
        c.client.search(query, scope=True, content_type=["legal"])
    except ValueError:
        _say("scope= with an explicit content_type=: refused client-side")
    else:
        raise AssertionError("scope= alongside content_type= should be refused")

    try:
        c.client.search(query, scope=True, attribute=["region:FR"])
    except ValueError:
        _say("scope= with an explicit attribute=: refused client-side")
    else:
        raise AssertionError("scope= alongside attribute= should be refused")

    if not c.scope_model:
        _say("completion mode: skipped, pass --scope-model <model> to exercise it")
        return

    # Completion mode: the API runs the LLM and hands back the filters it inferred.
    inferred = ContentType.scope(c.client, query, model=c.scope_model)
    done = inferred.completion
    # Also proves the wire really sends `scope_completion`: this is the SDK's one
    # aliased field, and a fixture can't prove the server side of an alias.
    assert done is not None, "model= must return a completion (wire: scope_completion)"
    _say(f"scope(model={c.scope_model!r}) → {inferred.filters()}")
    if done.warnings:
        _say(f"  warnings: {done.warnings}", typer.colors.YELLOW)
    assert done.raw_output, "the completion came back with no raw_output"

    narrowed = inferred.filters()
    assert set(narrowed) <= {"content_type", "attribute"}, (
        f"filters() grew a key the verbs don't take: {sorted(narrowed)}"
    )
    # An inferred scope outranks has_signal: the model answered, and the retrieval
    # gate doesn't get to veto it.
    if done.content_type or done.attribute:
        assert narrowed, "a completion inferred filters but filters() dropped them"
        if done.content_type:
            assert narrowed.get("content_type") == [done.content_type], (
                f"filters() says {narrowed.get('content_type')}, "
                f"completion says {done.content_type}"
            )
        _say(f"completion outranks has_signal={inferred.has_signal}: {narrowed}")

    # Not asserting on sources: an LLM-inferred filter can legitimately exclude
    # this corpus, which is a retrieval outcome and not an SDK failure.
    grounded = c.client.ask(query, workspaces=[ws], scope=inferred, max_results=5)
    assert grounded.answer, "ask(scope=<inferred>) returned an empty answer"
    if not grounded.results:
        _say("ask(scope=<inferred>) grounded on nothing", typer.colors.YELLOW)
    _say(f"ask(scope=<inferred>) → {len(grounded.results)} source chunk(s)")

    # Catalog + model: infer over the whole taxonomy, not the query-relevant slice.
    whole = ContentType.scope(
        c.client, query, model=c.scope_model, relevance_scoring=RelevanceScoring.none
    )
    assert whole.completion is not None, "catalog+model must still return a completion"
    _say(f"catalog+model → {whole.filters()}")


@step
def facet_filters(c: Ctx) -> None:
    """content_type= / attribute= on search and ask (needs the content_types step)."""
    ws = c.workspace()
    ct = c.content_type
    if ct is None:
        _say("nothing classified, run with --only content_types --only facet_filters")
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
def stream(c: Ctx) -> None:
    """ask(stream=True): sources → tokens → done, and composed with schema=."""
    ws = c.workspace()
    query = c.ask_query or f"What does the document say about {_topic(c)}?"

    sources, tokens, done = None, [], False
    for event in c.client.ask(query, workspaces=[ws], max_results=5, stream=True):
        if isinstance(event, SourcesEvent):
            assert sources is None, "sources arrived more than once"
            assert not tokens, "sources must arrive before any token"
            sources = event.results
        elif isinstance(event, TokenEvent):
            tokens.append(event.text)
        elif isinstance(event, DoneEvent):
            done = True
    assert done, "stream ended without a done event"
    assert tokens, "stream produced no tokens"
    answer = "".join(tokens)
    _say(f"{len(sources or [])} source(s), {len(tokens)} token event(s): {answer[:90]}")

    # The same items non-streaming ask returns, so a UI can show them right away.
    assert sources, "no sources event"
    assert sources[0].source.filename, "a source came back without a filename"

    # stream + structured output compose: the tokens spell out the JSON.
    text = "".join(
        e.text
        for e in c.client.ask(
            query, workspaces=[ws], schema=GroundedAnswer, stream=True
        )
        if isinstance(e, TokenEvent)
    )
    parsed = GroundedAnswer.model_validate_json(text)  # raises if off-schema
    _say(f"streamed structured output: confident={parsed.confident}")

    # A generator: nothing is sent until iteration, and closing early is clean.
    it = c.client.ask(query, workspaces=[ws], stream=True)
    next(it)
    it.close()
    _say("early close released the stream cleanly")


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
def binary(c: Ctx) -> None:
    """download (each purpose) → pages() vs parse() → thumbnail status gate."""
    f = c.uploaded()
    doc = c.docs[0]

    original = f.download()
    assert original == doc.read_bytes(), "download() did not return the bytes we sent"
    _say(f"download original: {len(original)} bytes, byte-identical to the upload")

    for purpose in (DownloadPurpose.rendered_pdf, DownloadPurpose.transcript):
        got = f.download(purpose)
        assert got, f"download({purpose}) returned nothing"
        _say(f"download {purpose}: {len(got)} bytes")

    pages = f.pages()
    assert pages, "pages() returned nothing for an embedded document"
    assert pages[0].markdown, "first page has no markdown"
    parsed = c.client.parse(path=doc).result.pages
    assert type(pages[0]) is type(parsed[0]), "pages() and parse() must share Page"
    assert len(pages) == len(parsed), f"pages(): {len(pages)}, parse(): {len(parsed)}"
    _say(f"pages(): {len(pages)} page(s), same Page model and count as parse()")

    # Thumbnails are generated independently of ingestion, so READY is not a given.
    f.refresh()
    status = f.thumbnail.status if f.thumbnail else None
    if status is ThumbnailStatus.READY:
        image = f.download_thumbnail()
        assert image, "thumbnail READY but the fetch returned nothing"
        _say(f"thumbnail READY: {len(image)} bytes")
    else:
        try:
            f.download_thumbnail()
        except NotFoundError:
            _say(f"thumbnail {status}: fetch raises NotFoundError, as documented")
        else:
            raise AssertionError(f"thumbnail is {status} but the fetch succeeded")


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
    scope_model: str = typer.Option(
        None,
        "--scope-model",
        help="LLM for the `scope` step's completion mode [default: skip it].",
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
        c = Ctx(client, documents, stamp, ask_query, search_query, scope_model)
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
