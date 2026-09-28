"""Content-type taxonomy + a file's facets, independent of the generated api types.

`ContentType` is a node in the company's content-type tree (path like
`legal:contract:nda`, with child nodes and attribute definitions). It's read-only
discovery, `ContentType.list()`, not an active-record: the endpoint returns a
nested tree, not a paginated flat list.

`Facet` is a content type *assigned to a file* together with the file's attribute
values on it (see `File.classify()` / `File.facets()`). `Attribute` is the shared
name/type/value shape used by both. `ContentTypeAction`/`ContentTypeResult` and
`FacetAction`/`FacetResult` are the write and result shapes of the two batch
endpoints, `ContentType.batch()` and `File.batch_facets()`.

`FacetScope` is what `ContentType.scope()` resolves: the taxonomy ranked against a
natural-language query, plus the `content_type`/`attribute` filters to narrow a
search with. `ScopeGroup`/`ScopedContentType`/`ScopeCompletion` are its parts, and
`resolve_scope()` is the coercion helper `ask`/`search` call for their `scope=`.

`ContentTypeRef` is what every "name a content type" parameter takes across the
SDK, here and on `File`/`ask`/`search`.
"""

from __future__ import annotations

# The list() classmethod shadows builtin list in annotations (class scope).
from builtins import list as _list
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lighton.enums import (
    AttributeType,
    ContentTypeActionType,
    FacetActionType,
    RelevanceScoring,
)
from lighton.utils import _compact, _path, _paths

if TYPE_CHECKING:
    from lighton._client import LightOn

_BASE = "/api/v3/content-types"

MAX_CONTENT_TYPE_ACTIONS = 50
"""Actions per `ContentType.batch()` call, the API's cap. Split a longer job yourself."""

MAX_FACET_ACTIONS = 50
"""Actions per `File.batch_facets()` call, the API's cap. Split a longer job yourself."""


class Attribute(BaseModel):
    """One attribute of a content type, a definition, or a value set on a file.

    Carries both the schema (type/required/choices) and, when read from a file's
    facets, the current `value`. `value` is None for bare definitions / when unset.
    """

    model_config = ConfigDict(extra="ignore")

    name: str = Field(description="Attribute identifier in snake_case.")
    label: str = Field("", description="Human-readable label.")
    type: str = Field(
        "", description="text, number, date, boolean, select, or multi-select."
    )
    value: Any = Field(
        None, description="Current value on the file; None for a definition/unset."
    )
    required: bool = Field(False, description="Whether the schema requires it.")
    choices: _list[str] = Field(
        default_factory=list, description="Allowed values for select/multi-select."
    )
    description: str = Field("", description="Optional attribute description.")


class ContentType(BaseModel):
    """A node in the content-type taxonomy."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(description="Full taxonomy path, e.g. legal:contract:nda.")
    code: str = Field(description="This node's own code segment.")
    label: str = Field(description="Human-readable label.")
    description: str = Field("", description="Free-text description.")
    source: str | None = Field(
        None, description="Where the type is defined (read-only)."
    )
    attributes: _list[Attribute] = Field(
        default_factory=list,
        description="Attribute definitions (present when include_attributes=True).",
    )
    children: _list[ContentType] = Field(
        default_factory=list, description="Child content types."
    )

    @classmethod
    def list(
        cls,
        client: LightOn,
        *,
        path: str | None = None,
        depth: int | None = None,
        include_attributes: bool = False,
        query: str | None = None,
    ) -> _list[ContentType]:
        """List the content-type taxonomy (top-level nodes, each with `children`).

        Args:
            client: The client to query with.
            path: Restrict to the subtree rooted at this path.
            depth: How many levels of children to return.
            include_attributes: Populate each node's `attributes` definitions.
            query: Free-text filter over labels/paths.

        Returns:
            The top-level content-type nodes.
        """
        params = _compact(
            path=path, depth=depth, include_attributes=include_attributes, query=query
        )
        data = client._request("GET", _BASE, params=params)
        return [cls.model_validate(n) for n in data["content_types"]]

    @classmethod
    def scope(
        cls,
        client: LightOn,
        query: str | None = None,
        *,
        max_results: int | None = None,
        threshold: float | None = None,
        model: str | None = None,
        relevance_scoring: Literal[RelevanceScoring.none] | None = None,
    ) -> FacetScope:
        """Rank the taxonomy against a question (POST /content-types/scope).

        Turns free text into the `content_type`/`attribute` filters `ask` and
        `search` take, so a caller doesn't have to know the taxonomy by heart.
        Three modes, by argument:

        - **prompt** (no `model`): scored content types plus `prompt_context`, a
          ready-made prompt for your own LLM. No `completion`.
        - **completion** (`model=`): the API runs that LLM itself and returns the
          inferred scope in `completion`, attribute filters included.
        - **catalog** (`relevance_scoring=RelevanceScoring.none`): every content
          type at score 0, `max_results`/`threshold` ignored. Pair it with `model`
          to infer over the whole taxonomy rather than the query-relevant slice.

        Nothing is stored: this is one stateless inference call.

        Args:
            client: The client to query with.
            query: The natural-language question (max 2000 chars). Omit it for the
                full schema catalog, which is what you want for a system prompt.
            max_results: Content types to return (1-100; server default 20).
            threshold: Score above which `has_signal` goes true (server default
                1.8). Pass 0 to disable the gate.
            model: Technical name of the LLM that infers the scope. Omit to get
                `prompt_context` and run your own. On `ask`, note this is a
                different model from its answer-generation `model`.
            relevance_scoring: Only `RelevanceScoring.none` is accepted here (skip
                scoring, return the whole catalog); omit for the default scoring.

        Returns:
            The resolved scope. Feed it to `ask`/`search` as `scope=`, or read
            `filters()` yourself.

        Raises:
            ValueError: If `relevance_scoring` is anything but
                `RelevanceScoring.none`, which the API rejects anyway, caught here
                to save the round trip.
        """
        if relevance_scoring is not None and relevance_scoring != RelevanceScoring.none:
            raise ValueError(
                f"scope() only accepts relevance_scoring=RelevanceScoring.none, "
                f"got {relevance_scoring}"
            )
        body = _compact(
            query=query,
            max_results=max_results,
            threshold=threshold,
            model=model,
            relevance_scoring=relevance_scoring,
        )
        return FacetScope.model_validate(
            client._request("POST", f"{_BASE}/scope", json=body)
        )

    # --- taxonomy writes ---------------------------------------------------
    # Mirrors File._facet: one helper posts the action, the named methods just
    # build it. Every action is idempotent server-side.
    @classmethod
    def _action(cls, client: LightOn, action: ContentTypeAction) -> Any:
        # ContentTypeAction._body() is the single wire encoder, shared with
        # batch(), so the single-action and batch bodies cannot drift apart.
        return client._request("POST", _BASE, json=action._body())

    @classmethod
    def templates(cls, client: LightOn) -> _list[Template]:
        """List the starter taxonomies you can `adopt()` (GET /content-types/templates).

        Args:
            client: The client to query with.

        Returns:
            The template root nodes, each with its `children` and an `attributes`
            map covering the whole subtree.
        """
        data = client._request("GET", f"{_BASE}/templates")
        return [Template.model_validate(n) for n in data["content_types"]]

    @classmethod
    def adopt(cls, client: LightOn, paths: _list[str]) -> _list[ContentType]:
        """Import starter trees from the template catalog into your taxonomy.

        Args:
            client: The client to write with.
            paths: Template root paths to import, e.g. `["legal", "finance"]`
                (see `templates()`).

        Returns:
            The imported top-level nodes.
        """
        data = cls._action(client, ContentTypeAction.adopt(paths))
        return [cls.model_validate(n) for n in data["content_types"]]

    @classmethod
    def define(
        cls,
        client: LightOn,
        code: str,
        label: str,
        *,
        parent: ContentTypeRef | None = None,
        description: str | None = None,
        inherit_attributes: bool | None = None,
    ) -> ContentType:
        """Create or update one node (POST /content-types, `define_content_type`).

        Idempotent: defining an existing code again updates it, so this is also
        how you rename a node.

        Args:
            client: The client to write with.
            code: This node's own segment, lowercase alphanumeric with hyphens
                (e.g. "employment-contract"); the server rejects anything else.
            label: Human-readable label.
            parent: Parent node or path; omit for a root node.
            description: Optional free-text description.
            inherit_attributes: Whether children inherit this node's attributes
                (server default True).

        Returns:
            The created (or updated) node.
        """
        return cls.model_validate(
            cls._action(
                client,
                ContentTypeAction.define(
                    code,
                    label,
                    parent=parent,
                    description=description,
                    inherit_attributes=inherit_attributes,
                ),
            )
        )

    @classmethod
    def undefine(cls, client: LightOn, content_type: ContentTypeRef) -> None:
        """Delete a node **and cascade its whole subtree**.

        Args:
            client: The client to write with.
            content_type: The node to delete (object or path string).

        Returns:
            None.
        """
        cls._action(client, ContentTypeAction.undefine(content_type))

    @classmethod
    def define_attribute(
        cls,
        client: LightOn,
        content_type: ContentTypeRef,
        name: str,
        attribute_type: AttributeType | str,
        *,
        choices: _list[str] | None = None,
        label: str | None = None,
        description: str | None = None,
        required: bool | None = None,
    ) -> Attribute:
        """Create or update an attribute column on a node.

        Args:
            client: The client to write with.
            content_type: The node to define it on (object or path string).
            name: Attribute identifier in snake_case.
            attribute_type: AttributeType, or the equivalent string.
            choices: Allowed values; **required** for select and multi-select,
                and rejected by the server for every other type.
            label: Human-readable label (defaults to a title-cased `name`).
            description: Optional description.
            required: Whether the schema requires a value (server default False).

        Returns:
            The created (or updated) attribute definition.

        Raises:
            ValueError: If a select/multi-select is missing `choices`, which the
                API rejects with a 422 anyway, caught here to save the round trip.
                Raised by `ContentTypeAction`, so it arrives as the pydantic
                `ValidationError` subclass.
        """
        return Attribute.model_validate(
            cls._action(
                client,
                ContentTypeAction.define_attribute(
                    content_type,
                    name,
                    attribute_type,
                    choices=choices,
                    label=label,
                    description=description,
                    required=required,
                ),
            )
        )

    @classmethod
    def undefine_attribute(
        cls, client: LightOn, content_type: ContentTypeRef, name: str
    ) -> None:
        """Remove an attribute column from a node.

        Args:
            client: The client to write with.
            content_type: The node it's defined on (object or path string).
            name: Attribute identifier to remove.

        Returns:
            None.
        """
        cls._action(client, ContentTypeAction.undefine_attribute(content_type, name))

    @classmethod
    def batch(
        cls, client: LightOn, actions: Sequence[ContentTypeAction | dict[str, Any]]
    ) -> _list[ContentTypeResult]:
        """Apply up to 50 taxonomy actions in one request (POST /content-types/batch).

        The batch form of adopt/define/undefine/define_attribute/
        undefine_attribute. Build the list with `ContentTypeAction`, whose
        constructors take the same arguments as those methods, so a whole tree and
        its attributes land together instead of one round trip each:

            ContentType.batch(client, [
                ContentTypeAction.adopt(["legal"]),
                ContentTypeAction.define_attribute(
                    "legal", "jurisdiction", AttributeType.select,
                    choices=["FR", "US"],
                ),
            ])

        The list is inert until it gets here, so the same one seeds many tenants.

        **Not transactional.** Field-level mistakes are caught up front, so a
        malformed action applies nothing. A domain error (an unknown parent path,
        a permission denial) stops at that action: everything before it is already
        applied, and the raised error carries its 0-based position on `.index`.
        Every action is idempotent, so correct that one and resend the whole list.

        Args:
            client: The client to write with.
            actions: The actions, in order, at most 50. `ContentTypeAction`
                objects, or raw action bodies as dicts for a verb the SDK doesn't
                model yet (mix freely). Empty is a local no-op. A longer job is
                yours to split: chunking here would report an index relative to a
                batch you never wrote.

        Returns:
            One ContentTypeResult per action, in the order sent, so `results[i]`
            belongs to `actions[i]`. Only ever complete: a failure raises instead.

        Raises:
            ValueError: If more than 50 actions are passed (refused here to save
                the round trip).
            LightOnAPIError: If an action fails. `.index` is the one that did, and
                the actions before it are already applied.
        """
        if not actions:
            return []
        if len(actions) > MAX_CONTENT_TYPE_ACTIONS:
            raise ValueError(
                f"a batch takes at most {MAX_CONTENT_TYPE_ACTIONS} actions, got "
                f"{len(actions)}; send them {MAX_CONTENT_TYPE_ACTIONS} at a time"
            )
        bodies = [a._body() if isinstance(a, ContentTypeAction) else a for a in actions]
        data = client._request("POST", f"{_BASE}/batch", json={"actions": bodies})
        return [ContentTypeResult.model_validate(r) for r in data["results"]]


class Template(ContentType):
    """A starter taxonomy from the catalog, what `adopt()` imports.

    Same tree as a `ContentType` except for `attributes`: on a template it's a
    **map** from node path to that node's attribute definitions (the whole tree's
    attributes hang off the root), not this node's own list.
    """

    attributes: dict[str, _list[Attribute]] = Field(  # type: ignore[assignment]
        default_factory=dict,
        description="Attribute definitions per node path, for the whole subtree.",
    )


class ContentTypeAction(BaseModel):
    """One taxonomy write, applied by `ContentType.batch()`.

    Build these with the constructors, not the fields: each takes the same
    arguments in the same order as the `ContentType` classmethod of the same name
    (minus `client`), so a batch is a transcription of the single-action calls.

        ContentType.batch(client, [
            ContentTypeAction.define("compliance", "Compliance"),
            ContentTypeAction.define_attribute(
                "compliance", "owner", AttributeType.text
            ),
        ])

    One wide model rather than five, which is how the API models it too
    (`ContentTypeActionRequest`): the fields are the union of the five action
    shapes, and a validator enforces the narrow contract per verb. Each field
    below names the verbs it belongs to.

    Nothing is sent until the list reaches `batch()`, so one list seeds many
    tenants.
    """

    # forbid, not ignore: this is a write model, a misspelled field must fail
    # loudly rather than vanish from the body. Raw dicts are the unmodelled escape.
    model_config = ConfigDict(extra="forbid")

    action: ContentTypeActionType = Field(
        description="The write to perform, the API's verb (see ContentTypeActionType)."
    )
    content_types: _list[str] | None = Field(
        None, description="Template root paths to import; adopt only."
    )
    parent_path: str | None = Field(
        None, description="Parent node path; define only, omitted for a root."
    )
    code: str | None = Field(
        None,
        description="The node's own segment, lowercase with hyphens; define only.",
    )
    content_type_path: str | None = Field(
        None,
        description=(
            "Node the action applies to, e.g. legal:contract:nda; every verb but "
            "adopt and define."
        ),
    )
    label: str | None = Field(
        None,
        description=(
            "Human-readable label, required by define, optional on define_attribute."
        ),
    )
    description: str | None = Field(
        None, description="Free-text description; define and define_attribute."
    )
    inherit_attributes: bool | None = Field(
        None,
        description=(
            "Whether children inherit this node's attributes (server default "
            "True); define only."
        ),
    )
    name: str | None = Field(
        None,
        description=(
            "Attribute identifier in snake_case; define_attribute and "
            "undefine_attribute."
        ),
    )
    attribute_type: AttributeType | str | None = Field(
        None,
        description=(
            "AttributeType, or the equivalent string (the API also accepts the "
            "multi_select/multiselect/rich_text/richtext aliases, which skip the "
            "local choices check); define_attribute only."
        ),
    )
    required: bool | None = Field(
        None,
        description=(
            "Whether the schema requires a value (server default False); "
            "define_attribute only."
        ),
    )
    choices: _list[str] | None = Field(
        None,
        description=(
            "Allowed values, **required** for select and multi-select and "
            "rejected for every other type; define_attribute only."
        ),
    )

    @model_validator(mode="after")
    def _each_verb_needs_its_fields(self) -> ContentTypeAction:
        """Refuse locally what the API would 422: the narrow contract per verb."""
        needed = {
            ContentTypeActionType.adopt: ("content_types",),
            ContentTypeActionType.define_content_type: ("code", "label"),
            ContentTypeActionType.undefine_content_type: ("content_type_path",),
            ContentTypeActionType.define_attribute: (
                "content_type_path",
                "name",
                "attribute_type",
            ),
            ContentTypeActionType.undefine_attribute: ("content_type_path", "name"),
        }
        missing = [f for f in needed[self.action] if not getattr(self, f)]
        if missing:
            raise ValueError(f"{self.action} needs {', '.join(missing)}")
        # ponytail: `AttributeType` only, which a StrEnum makes cover the canonical
        # strings too. The API additionally accepts the multi_select/multiselect/
        # rich_text/richtext aliases; those reach its 422. Matching them here would
        # mean hand-keeping a copy of a vocabulary we don't own, to save a round
        # trip for a caller who deliberately went around the enum.
        if (
            self.action == ContentTypeActionType.define_attribute
            and self.attribute_type
            in (AttributeType.select, AttributeType.multi_select)
            and not self.choices
        ):
            raise ValueError(f"{self.attribute_type} needs choices")
        return self

    @classmethod
    def adopt(cls, paths: _list[str]) -> ContentTypeAction:
        """Import starter trees, the batch form of `ContentType.adopt()`.

        Args:
            paths: Template root paths to import, e.g. `["legal", "finance"]`
                (see `ContentType.templates()`).

        Returns:
            The action, unsent.
        """
        return cls(action=ContentTypeActionType.adopt, content_types=paths)

    @classmethod
    def define(
        cls,
        code: str,
        label: str,
        *,
        parent: ContentTypeRef | None = None,
        description: str | None = None,
        inherit_attributes: bool | None = None,
    ) -> ContentTypeAction:
        """Create or update a node, the batch form of `ContentType.define()`.

        Args:
            code: This node's own segment, lowercase alphanumeric with hyphens.
            label: Human-readable label.
            parent: Parent node or path; omit for a root node.
            description: Optional free-text description.
            inherit_attributes: Whether children inherit this node's attributes
                (server default True).

        Returns:
            The action, unsent.
        """
        return cls(
            action=ContentTypeActionType.define_content_type,
            code=code,
            label=label,
            parent_path=_path(parent) if parent is not None else None,
            description=description,
            inherit_attributes=inherit_attributes,
        )

    @classmethod
    def undefine(cls, content_type: ContentTypeRef) -> ContentTypeAction:
        """Delete a node and its subtree, the batch form of `ContentType.undefine()`.

        Args:
            content_type: The node to delete (object or path string).

        Returns:
            The action, unsent.
        """
        return cls(
            action=ContentTypeActionType.undefine_content_type,
            content_type_path=_path(content_type),
        )

    @classmethod
    def define_attribute(
        cls,
        content_type: ContentTypeRef,
        name: str,
        attribute_type: AttributeType | str,
        *,
        choices: _list[str] | None = None,
        label: str | None = None,
        description: str | None = None,
        required: bool | None = None,
    ) -> ContentTypeAction:
        """Add an attribute, the batch form of `ContentType.define_attribute()`.

        Args:
            content_type: The node to define it on (object or path string).
            name: Attribute identifier in snake_case.
            attribute_type: AttributeType, or the equivalent string.
            choices: Allowed values; **required** for select and multi-select,
                and rejected by the server for every other type.
            label: Human-readable label (defaults to a title-cased `name`).
            description: Optional description.
            required: Whether the schema requires a value (server default False).

        Returns:
            The action, unsent.

        Raises:
            ValueError: If a select/multi-select is missing `choices`, which the
                API rejects with a 422 anyway, caught here to save the round trip.
        """
        return cls(
            action=ContentTypeActionType.define_attribute,
            content_type_path=_path(content_type),
            name=name,
            attribute_type=attribute_type,
            choices=choices,
            label=label,
            description=description,
            required=required,
        )

    @classmethod
    def undefine_attribute(
        cls, content_type: ContentTypeRef, name: str
    ) -> ContentTypeAction:
        """Remove an attribute, the batch form of `ContentType.undefine_attribute()`.

        Args:
            content_type: The node it's defined on (object or path string).
            name: Attribute identifier to remove.

        Returns:
            The action, unsent.
        """
        return cls(
            action=ContentTypeActionType.undefine_attribute,
            content_type_path=_path(content_type),
            name=name,
        )

    def _body(self) -> dict[str, Any]:
        # The one place that knows the wire field names: the single-action
        # classmethods post exactly this too, so single and batch can't drift.
        # Every unset field simply stays out, which is what _compact did here
        # before, and no content-type field is meaningfully null on the wire the
        # way FacetAction's `value` is, so there is no special case to carry.
        return self.model_dump(exclude_none=True)


class ContentTypeResult(BaseModel):
    """What one action in a `ContentType.batch()` returned, in request order.

    Every result you receive succeeded: the endpoint fails fast, so a failing
    action raises (see `LightOnAPIError.index`) and no results come back at all. A
    returned list is therefore always complete and in order, so `results[i]` is the
    outcome of `actions[i]`.
    """

    model_config = ConfigDict(extra="ignore")

    status: int = Field(
        description=(
            "Per-action status: 201 created, 200 already applied/updated, 204 for "
            "the removals (undefine, undefine_attribute)."
        )
    )
    data: dict[str, Any] | None = Field(
        None,
        description=(
            "What the action returned, None for the 204 verbs. The content-type "
            "verbs give a node, the attribute ones an attribute definition, and "
            "adopt the imported roots. Left a raw dict: it differs per verb, so "
            "there is no one model to validate it into."
        ),
    )


class ScopedContentType(BaseModel):
    """One content type scored against a query by `ContentType.scope()`.

    It carries `.path`, so it is a `ContentTypeRef`: `search(content_type=[hit])`
    and `doc.classify(hit)` both work, and type-check.
    """

    model_config = ConfigDict(extra="ignore")

    path: str = Field(description="Full taxonomy path, e.g. legal:contract:nda.")
    label: str = Field(description="Human-readable label.")
    root: str = Field(description="Path of the tree this node belongs to.")
    score: float = Field(
        description="Relevance to the query; 0 when scoring was skipped."
    )
    chunk_count: int = Field(description="Chunks matching the query under this type.")
    doc_count: int = Field(description="Documents classified under this type.")
    attributes: _list[Attribute] = Field(
        default_factory=list,
        description="Attribute definitions on this type; `value` is always None here.",
    )


ContentTypeRef = ContentType | ScopedContentType | str
"""Anything that names a content type: a taxonomy node, a scored hit, or a path.

Exactly what `_path()`/`_paths()` coerce, so every parameter that takes a content
type takes all three. Declared once here rather than spelled out per signature:
it is one rule (*we accept a `.path`*), and `ScopedContentType` was added to it
without touching the fifteen signatures that state it.
"""


class ScopeGroup(BaseModel):
    """The scored content types of one taxonomy tree, as `scope()` groups them."""

    model_config = ConfigDict(extra="ignore")

    root: str = Field(description="Path of the tree's root node.")
    root_label: str = Field(description="Human-readable label of the root.")
    max_score: float = Field(description="Best score among this group's types.")
    content_types: _list[ScopedContentType] = Field(
        default_factory=list, description="The tree's scored content types."
    )


class ScopeCompletion(BaseModel):
    """The LLM's inferred scope, present only when `scope()` was given a `model`.

    Its `content_type`/`attribute` are already normalized to the paths and filter
    syntax `ask`/`search` expect, which is what `FacetScope.filters()` hands back.
    """

    model_config = ConfigDict(extra="ignore")

    content_type: str | None = Field(
        None, description="Inferred content-type path, None when it inferred none."
    )
    attribute: _list[str] = Field(
        default_factory=list,
        description='Inferred attribute filters, e.g. ["filing_date:>=2023-01-01"].',
    )
    raw_output: str = Field("", description="The model's unparsed output.")
    normalized: bool = Field(
        False, description="Whether a label had to be mapped onto its attribute name."
    )
    warnings: _list[str] = Field(
        default_factory=list,
        description=(
            "Why inference degraded, empty in the happy path. A failed model call "
            "lands here rather than failing the request."
        ),
    )


class FacetScope(BaseModel):
    """A search scope resolved from a question, what `ContentType.scope()` returns."""

    # populate_by_name so `completion` works as a field name too, not just the
    # `scope_completion` the wire sends.
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    has_signal: bool = Field(
        description="Whether any content type scored above `threshold`."
    )
    groups: _list[ScopeGroup] = Field(
        default_factory=list, description="Scored content types, grouped by tree."
    )
    prompt_context: str | None = Field(
        None,
        description=(
            "LLM-ready description of the matched schema. Feed it to your own model "
            "when you resolve the scope yourself (no `model=`)."
        ),
    )
    prompt_version: str | None = Field(
        None,
        description=(
            "Hash of the prompt template and the data behind it, for reproducing a "
            "run. Same value means the same prompt was built."
        ),
    )
    completion: ScopeCompletion | None = Field(
        None,
        alias="scope_completion",
        description="The LLM's inferred scope; None unless `scope()` got a `model`.",
    )

    @property
    def content_types(self) -> _list[ScopedContentType]:
        """Every scored content type across the groups, best score first.

        Returns:
            The flattened, score-ordered hits. `groups` keeps the server's grouping
            if you want it by tree.
        """
        hits = [ct for group in self.groups for ct in group.content_types]
        return sorted(hits, key=lambda ct: ct.score, reverse=True)

    def filters(self) -> dict[str, _list[str]]:
        """The `content_type`/`attribute` filters this scope narrows to.

        Passing the scope itself, `client.search(query, scope=scope)`, applies
        these for you; read them here to see (or log) what a scope would narrow
        to before spending the search on it. Pass them by keyword rather than
        splatting the dict, which a type checker can't match to the signature:

            client.search(query, content_type=scope.filters().get("content_type"))

        Precedence:

        1. A `completion` that inferred anything wins. That is an explicit answer
           from the model, and `has_signal` (a retrieval-score gate) must not veto it.
        2. Otherwise, no signal means no narrowing, so `{}`.
        3. Otherwise the scored paths, which is retrieval-only narrowing. **Every**
           scored path, not just the best ones: `threshold` gates `has_signal` for
           the whole scope and isn't echoed per hit, so there is nothing to cut on
           here. Narrowing to the top few is `scope(..., max_results=3)` at resolve
           time. No attribute filters either: inferring those needs a `model`.

        Returns:
            A dict holding `content_type` and/or `attribute`, empty when the scope
            says to narrow nothing. A key is absent rather than empty, so a
            missing filter reads the same as one never asked for.
        """
        done = self.completion
        if done is not None and (done.content_type or done.attribute):
            narrowed: dict[str, _list[str]] = {}
            if done.content_type:
                narrowed["content_type"] = [done.content_type]
            if done.attribute:
                narrowed["attribute"] = _list(done.attribute)
            return narrowed
        if not self.has_signal:
            return {}
        paths = [ct.path for ct in self.content_types]
        return {"content_type": paths} if paths else {}


class Facet(BaseModel):
    """A content type assigned to a file, with the file's attribute values on it."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(description="Assigned content-type path on the file.")
    label: str = Field(description="Human-readable content-type label.")
    attributes: _list[Attribute] = Field(
        default_factory=list, description="Attribute values set on the file."
    )


class FacetAction(BaseModel):
    """One classification write, applied by `File.batch_facets()`.

    Build these with the constructors, not the fields: each takes the same
    arguments in the same order as the `File` method of the same name, so a batch
    is a transcription of the single-action calls it replaces.

        doc.batch_facets([
            FacetAction.classify(nda),
            FacetAction.set_attribute(nda, "jurisdiction", "FR"),
        ])

    Nothing is sent until the list reaches a file, so one list applies to many.
    """

    # forbid, not ignore: this is a write model, a misspelled field must fail
    # loudly rather than vanish from the body. Raw dicts are the unmodelled escape.
    model_config = ConfigDict(extra="forbid")

    action: FacetActionType = Field(
        description="The write to perform, the API's verb (see FacetActionType)."
    )
    content_type_path: str = Field(
        description="Content type the action applies to, e.g. legal:contract:nda."
    )
    attribute_name: str | None = Field(
        None,
        description="Attribute identifier in snake_case; required by the value verbs.",
    )
    value: Any = Field(
        None,
        description=(
            "Value for set_attribute; shape follows the attribute type (string, "
            "number, date 'YYYY-MM-DD', bool, or list[str] for multi-select)."
        ),
    )

    @model_validator(mode="after")
    def _value_actions_need_an_attribute(self) -> FacetAction:
        """The API 422s a value verb with no attribute_name; refuse it locally."""
        value_verbs = (FacetActionType.set_value, FacetActionType.clear_value)
        if self.action in value_verbs and not self.attribute_name:
            raise ValueError(f"{self.action} needs an attribute_name")
        return self

    @classmethod
    def classify(cls, content_type: ContentTypeRef) -> FacetAction:
        """Assign a content type, the batch form of `File.classify()`.

        Args:
            content_type: The content type to assign (object or path string).

        Returns:
            The action, unsent.
        """
        return cls(
            action=FacetActionType.classify, content_type_path=_path(content_type)
        )

    @classmethod
    def unclassify(cls, content_type: ContentTypeRef) -> FacetAction:
        """Remove a content-type assignment, the batch form of `File.unclassify()`.

        Args:
            content_type: The content type to unassign (object or path string).

        Returns:
            The action, unsent.
        """
        return cls(
            action=FacetActionType.unclassify, content_type_path=_path(content_type)
        )

    @classmethod
    def set_attribute(
        cls, content_type: ContentTypeRef, name: str, value: Any
    ) -> FacetAction:
        """Set an attribute value, the batch form of `File.set_attribute()`.

        Args:
            content_type: The assigned content type (object or path string).
            name: Attribute identifier (snake_case).
            value: The value; shape depends on the attribute type (string, number,
                date "YYYY-MM-DD", bool, or list[str] for multi-select).

        Returns:
            The action, unsent.
        """
        return cls(
            action=FacetActionType.set_value,
            content_type_path=_path(content_type),
            attribute_name=name,
            value=value,
        )

    @classmethod
    def clear_attribute(cls, content_type: ContentTypeRef, name: str) -> FacetAction:
        """Clear an attribute value, the batch form of `File.clear_attribute()`.

        Args:
            content_type: The assigned content type (object or path string).
            name: Attribute identifier to clear.

        Returns:
            The action, unsent.
        """
        return cls(
            action=FacetActionType.clear_value,
            content_type_path=_path(content_type),
            attribute_name=name,
        )

    def _body(self) -> dict[str, Any]:
        # The one place that knows the wire field names: the single-action methods
        # on File post exactly this too, so single and batch can't drift.
        body: dict[str, Any] = {
            "action": self.action,
            "content_type_path": self.content_type_path,
        }
        if self.attribute_name is not None:
            body["attribute_name"] = self.attribute_name
        if self.action == FacetActionType.set_value:
            body["value"] = self.value  # sent even when None, the server decides
        return body


class FacetResult(BaseModel):
    """What one action in a `File.batch_facets()` returned, in request order.

    Every result you receive succeeded: the endpoint fails fast, so a failing
    action raises (see `LightOnAPIError.index`) and no results come back at all. A
    returned list is therefore always complete and in order, so `results[i]` is the
    outcome of `actions[i]`.
    """

    model_config = ConfigDict(extra="ignore")

    status: int = Field(
        description=(
            "Per-action status: 201 created, 200 already applied/updated, 204 for "
            "the removals (unclassify, clear_attribute)."
        )
    )
    data: dict[str, Any] | None = Field(
        None,
        description=(
            "What the action returned, None for the 204 verbs. classify gives "
            "{content_type_path, label}; set_attribute gives {name, value, "
            "content_type_path, label}. Left a raw dict: it differs per verb, so "
            "there is no one model to validate it into."
        ),
    )


def resolve_scope(
    client: LightOn,
    query: str,
    scope: FacetScope | bool,
    content_type: _list[ContentTypeRef] | None,
    attribute: _list[str] | None,
) -> tuple[_list[str] | None, _list[str] | None]:
    """The `content_type`/`attribute` a verb should send, applying `scope=` if asked.

    The one place that knows what `scope=` means, so `ask` and `search` can't
    drift (same reasoning as `FacetAction._body()`). `True` resolves the scope from
    the verb's own query with no `model`, which is retrieval-only narrowing and
    costs one extra request but no LLM call. It takes the endpoint's defaults, so
    it narrows to as many as 20 content types, weak matches included: a loose net,
    not a precise one. Tighter narrowing is `ContentType.scope(client, query,
    max_results=3)` passed in, and a `FacetScope` you resolved yourself is applied
    as-is, attribute filters included.

    Args:
        client: The client to resolve with, used only when `scope` is True.
        query: The verb's query, what an unresolved scope is inferred from.
        scope: False for no scoping, True to resolve one, or an already-resolved
            `FacetScope`.
        content_type: The verb's explicit `content_type` argument.
        attribute: The verb's explicit `attribute` argument.

    Returns:
        The `(content_type_paths, attribute)` pair to put in the request body.

    Raises:
        ValueError: If `scope` is combined with an explicit `content_type` or
            `attribute`. Merging them silently would hide which filters ran.
    """
    if not scope:  # False, and a FacetScope is always truthy
        return _paths(content_type), attribute
    if content_type is not None or attribute is not None:
        raise ValueError(
            "scope= replaces content_type=/attribute=; pass the scope or the "
            "explicit filters, not both"
        )
    resolved = (
        scope if isinstance(scope, FacetScope) else ContentType.scope(client, query)
    )
    narrowed = resolved.filters()
    return narrowed.get("content_type"), narrowed.get("attribute")


ContentType.model_rebuild()  # resolve the self-referential `children` forward ref
Template.model_rebuild()
