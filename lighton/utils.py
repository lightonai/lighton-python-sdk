"""Request-body helpers shared by the primary verbs."""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator
from pydantic import BaseModel

_DRAFT = "https://json-schema.org/draft/2020-12/schema"


def _compact(**kw: Any) -> dict[str, Any]:
    """Request body from kwargs, dropping None so the server applies its defaults."""
    return {k: v for k, v in kw.items() if v is not None}


def _ids(items: list[int] | list[Any] | None) -> list[int] | None:
    """Coerce a list of resources or ints to a list of ids (duck-typed on `.id`)."""
    if items is None:
        return None
    return [x if isinstance(x, int) else x.id for x in items]


def _inline_refs(node: Any, defs: dict[str, Any]) -> Any:
    """Replace every ``$ref`` into ``$defs`` with the resolved subschema, inline.

    vLLM's guided-generation grammar wants a self-contained schema, so `$defs`/
    `$ref` are flattened away. Sibling keywords on the ref (e.g. `description`)
    win over the resolved target.

    ponytail: recurses through refs, so a self-referential model blows the stack.
    Guided generation can't express unbounded recursion anyway, add a seen-set
    guard if such a model ever needs to reach here.
    """
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            target = defs[ref.rsplit("/", 1)[-1]]
            siblings = {
                k: _inline_refs(v, defs) for k, v in node.items() if k != "$ref"
            }
            return {**_inline_refs(target, defs), **siblings}
        return {k: _inline_refs(v, defs) for k, v in node.items()}
    if isinstance(node, list):
        return [_inline_refs(x, defs) for x in node]
    return node


def _collapse_nullable(node: Any) -> Any:
    """Rewrite ``anyOf: [{type: X}, {type: null}]`` as ``type: [X, "null"]``.

    Matches the shape vLLM examples use. Only collapses when every branch is a
    bare ``{"type": ...}``, a branch carrying `format`/`enum`/etc. can't fold
    into a type array, so it's left as `anyOf`.
    """
    if isinstance(node, dict):
        branches = node.get("anyOf")
        if isinstance(branches, list) and all(
            isinstance(b, dict) and set(b) == {"type"} for b in branches
        ):
            types = [b["type"] for b in branches]
            rest = {k: _collapse_nullable(v) for k, v in node.items() if k != "anyOf"}
            return {**rest, "type": types}
        return {k: _collapse_nullable(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_collapse_nullable(x) for x in node]
    return node


def validate_response_format_json(schema: dict[str, Any]) -> dict[str, Any]:
    """Validate a raw response_format schema against the draft-2020-12 meta-schema.

    For dict schemas passed straight through to vLLM (no pydantic model to vouch
    for them), this catches a malformed schema client-side instead of at the API.

    Args:
        schema: A dict holding a JSON Schema.

    Returns:
        The same schema, unchanged, once validated.

    Raises:
        jsonschema.exceptions.SchemaError: If it is not a valid JSON Schema.
    """
    Draft202012Validator.check_schema(schema)
    return schema


def convert_pydantic_to_response_format_json(model: type[BaseModel]) -> dict[str, Any]:
    """Convert a pydantic model class to a vLLM guided-generation `response_format` schema.

    Runs `model_json_schema()`, then normalizes: `$defs`/`$ref` inlined into a
    self-contained schema, nullable `anyOf` collapsed to `type: [X, "null"]`, and
    the draft-2020-12 `$schema` marker added.

    Args:
        model: The pydantic model class describing the extraction target.

    Returns:
        A self-contained JSON Schema dict suitable for vLLM guided generation.
    """
    raw = model.model_json_schema()
    defs = raw.get("$defs", {})
    inlined = _inline_refs({k: v for k, v in raw.items() if k != "$defs"}, defs)
    return {"$schema": _DRAFT, **_collapse_nullable(inlined)}
