"""Content-type taxonomy + a file's facets, independent of the generated api types.

`ContentType` is a node in the company's content-type tree (path like
`legal:contract:nda`, with child nodes and attribute definitions). It's read-only
discovery, `ContentType.list()`, not an active-record: the endpoint returns a
nested tree, not a paginated flat list.

`Facet` is a content type *assigned to a file* together with the file's attribute
values on it (see `File.classify()` / `File.facets()`). `Attribute` is the shared
name/type/value shape used by both.
"""

from __future__ import annotations

# The list() classmethod shadows builtin list in annotations (class scope).
from builtins import list as _list
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from lighton.enums import AttributeType
from lighton.utils import _compact, _path

if TYPE_CHECKING:
    from lighton._client import LightOn

_BASE = "/api/v3/content-types"


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

    # --- taxonomy writes ---------------------------------------------------
    # Mirrors File._facet: one helper posts the action, the named methods just
    # name their fields. Every action is idempotent server-side.
    @classmethod
    def _action(cls, client: LightOn, action: str, **fields: Any) -> Any:
        return client._request("POST", _BASE, json=_compact(action=action, **fields))

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
        data = cls._action(client, "adopt", content_types=paths)
        return [cls.model_validate(n) for n in data["content_types"]]

    @classmethod
    def define(
        cls,
        client: LightOn,
        code: str,
        label: str,
        *,
        parent: ContentType | str | None = None,
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
                "define_content_type",
                code=code,
                label=label,
                parent_path=_path(parent) if parent is not None else None,
                description=description,
                inherit_attributes=inherit_attributes,
            )
        )

    @classmethod
    def undefine(cls, client: LightOn, content_type: ContentType | str) -> None:
        """Delete a node **and cascade its whole subtree**.

        Args:
            client: The client to write with.
            content_type: The node to delete (object or path string).

        Returns:
            None.
        """
        cls._action(
            client, "undefine_content_type", content_type_path=_path(content_type)
        )

    @classmethod
    def define_attribute(
        cls,
        client: LightOn,
        content_type: ContentType | str,
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
        """
        if (
            attribute_type in (AttributeType.select, AttributeType.multi_select)
            and not choices
        ):
            raise ValueError(f"{attribute_type} needs choices")
        return Attribute.model_validate(
            cls._action(
                client,
                "define_attribute",
                content_type_path=_path(content_type),
                name=name,
                attribute_type=attribute_type,
                choices=choices,
                label=label,
                description=description,
                required=required,
            )
        )

    @classmethod
    def undefine_attribute(
        cls, client: LightOn, content_type: ContentType | str, name: str
    ) -> None:
        """Remove an attribute column from a node.

        Args:
            client: The client to write with.
            content_type: The node it's defined on (object or path string).
            name: Attribute identifier to remove.

        Returns:
            None.
        """
        cls._action(
            client,
            "undefine_attribute",
            content_type_path=_path(content_type),
            name=name,
        )

    @classmethod
    def batch(
        cls, client: LightOn, actions: _list[dict[str, Any]]
    ) -> _list[dict[str, Any]]:
        """Apply several taxonomy actions in one request (POST /content-types/batch).

        Each entry is the body a single-action method would send, so a tree and
        its attributes land together instead of one round trip each:

            ContentType.batch(client, [
                {"action": "adopt", "content_types": ["legal"]},
                {"action": "define_attribute", "content_type_path": "legal",
                 "name": "jurisdiction", "attribute_type": "select",
                 "choices": ["FR", "US"]},
            ])

        Args:
            client: The client to write with.
            actions: The action bodies, in order.

        Returns:
            One `{"status": ..., "data": ...}` entry per action, in the same
            order. `data` is a node for the content-type actions and an attribute
            for the attribute ones, so it's left as raw dicts rather than guessed
            into one model.
        """
        data = client._request("POST", f"{_BASE}/batch", json={"actions": actions})
        return data["results"]


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


class Facet(BaseModel):
    """A content type assigned to a file, with the file's attribute values on it."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(description="Assigned content-type path on the file.")
    label: str = Field(description="Human-readable content-type label.")
    attributes: _list[Attribute] = Field(
        default_factory=list, description="Attribute values set on the file."
    )


ContentType.model_rebuild()  # resolve the self-referential `children` forward ref
Template.model_rebuild()
