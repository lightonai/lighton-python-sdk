"""Request-body helpers shared by the primary verbs."""

from __future__ import annotations

from typing import Any


def _compact(**kw: Any) -> dict[str, Any]:
    """Request body from kwargs, dropping None so the server applies its defaults."""
    return {k: v for k, v in kw.items() if v is not None}


def _ids(items: list[int] | list[Any] | None) -> list[int] | None:
    """Coerce a list of resources or ints to a list of ids (duck-typed on `.id`)."""
    if items is None:
        return None
    return [x if isinstance(x, int) else x.id for x in items]
