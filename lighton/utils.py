"""Request-body helpers shared by the primary verbs."""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel

_DRAFT = "https://json-schema.org/draft/2020-12/schema"


def _compact(**kw: Any) -> dict[str, Any]:
    """Request body from kwargs, dropping None so the server applies its defaults."""
    return {k: v for k, v in kw.items() if v is not None}


def _id(item: int | Any) -> int:
    """Coerce a resource or an int to its id (duck-typed on `.id`)."""
    return item if isinstance(item, int) else item.id


def _ids(items: list[int] | list[Any] | None) -> list[int] | None:
    """Coerce a list of resources or ints to a list of ids (duck-typed on `.id`)."""
    if items is None:
        return None
    return [_id(x) for x in items]


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
            name = ref.rsplit("/", 1)[-1]
            if name not in defs:
                raise SchemaError(f"unresolved $ref {ref!r}: no such entry in $defs")
            target = defs[name]
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

    For dict schemas handed to vLLM without a pydantic model to vouch for them,
    this catches a malformed schema client-side instead of at the API.

    Args:
        schema: A dict holding a JSON Schema.

    Returns:
        The same schema, unchanged, once validated.

    Raises:
        jsonschema.exceptions.SchemaError: If it is not a valid JSON Schema.
    """
    Draft202012Validator.check_schema(schema)
    return schema


def normalize_response_format_json(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize a JSON Schema into the self-contained shape vLLM wants.

    `$defs`/`$ref` inlined, nullable `anyOf` collapsed to `type: [X, "null"]`,
    draft-2020-12 `$schema` marker added (an existing one is kept). The endpoint
    rejects `$ref`, so every schema goes through here, whether it came from a
    pydantic model or was passed in as a dict.

    Args:
        schema: A dict holding a JSON Schema, possibly with `$defs`/`$ref`.

    Returns:
        An equivalent self-contained schema, free of `$defs`/`$ref`.

    Raises:
        jsonschema.exceptions.SchemaError: If a `#/$defs/` ref has no target.
    """
    defs = schema.get("$defs", {})
    inlined = _inline_refs({k: v for k, v in schema.items() if k != "$defs"}, defs)
    return {"$schema": _DRAFT, **_collapse_nullable(inlined)}


def convert_pydantic_to_response_format_json(model: type[BaseModel]) -> dict[str, Any]:
    """Convert a pydantic model class to a vLLM guided-generation `response_format` schema.

    Runs `model_json_schema()` through `normalize_response_format_json`, which a
    nested model needs: pydantic emits `$defs`/`$ref` for every sub-model and the
    endpoint rejects those.

    Args:
        model: The pydantic model class describing the extraction target.

    Returns:
        A self-contained JSON Schema dict suitable for vLLM guided generation.
    """
    return normalize_response_format_json(model.model_json_schema())


def as_json_schema(schema: type[BaseModel] | dict[str, Any]) -> dict[str, Any]:
    """Either guided-generation input → the self-contained schema to send.

    Shared by `extract` (`schema`, the extraction target) and `ask` (`schema` →
    `response_format`, constraining the answer). A dict is validated against the
    JSON-Schema meta-schema (raises on malformed), then normalized; a pydantic
    model class is converted, which normalizes too. Both go through
    `normalize_response_format_json` because the endpoints reject `$ref`, and a
    dict hand-built from `model_json_schema()` carries them just as a class does.

    Args:
        schema: A pydantic model class or a dict holding a JSON Schema.

    Returns:
        A self-contained JSON Schema dict, free of `$defs`/`$ref`.

    Raises:
        jsonschema.exceptions.SchemaError: If a dict schema is malformed.
        TypeError: If `schema` is neither a dict nor a pydantic model class.
    """
    if isinstance(schema, dict):
        return normalize_response_format_json(validate_response_format_json(schema))
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return convert_pydantic_to_response_format_json(schema)
    raise TypeError("schema must be a pydantic BaseModel subclass or a dict")
