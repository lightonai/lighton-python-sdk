"""Content-type taxonomy + a file's facets, independent of the generated api types.

`ContentType` is a node in the company's content-type tree (path like
`legal:contract:nda`, with child nodes and attribute definitions). It's read-only
discovery — `ContentType.list()` — not an active-record: the endpoint returns a
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

from lighton.utils import _compact

if TYPE_CHECKING:
    from lighton._client import LightOn

_BASE = "/api/v3/content-types"


class Attribute(BaseModel):
    """One attribute of a content type — a definition, or a value set on a file.

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


class Facet(BaseModel):
    """A content type assigned to a file, with the file's attribute values on it."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(description="Assigned content-type path on the file.")
    label: str = Field(description="Human-readable content-type label.")
    attributes: _list[Attribute] = Field(
        default_factory=list, description="Attribute values set on the file."
    )


ContentType.model_rebuild()  # resolve the self-referential `children` forward ref
