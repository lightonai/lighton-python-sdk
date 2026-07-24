"""Tag schema + management, independent of the auto-generated api types.

Active-record style (see `_ActiveRecord`), but the tags API is **list/create/
delete only**, there's no `GET /tags/<id>`, so `get()`/`refresh()` are
unsupported and raise. Tags scope `ask`/`search` (see the `tags=` param there).
"""

from __future__ import annotations

# The list() classmethod shadows builtin list in annotations (class scope).
from builtins import list as _list
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar, NoReturn

from pydantic import Field

from lighton._active_record import _ActiveRecord

if TYPE_CHECKING:
    from lighton._client import LightOn

_BASE = "/api/v3/tags"
_NO_GET = "the tags API has no single-tag GET; use Tag.list(client)"


class Tag(_ActiveRecord):
    _base: ClassVar[str] = _BASE
    _resource: ClassVar[str] = "tag"

    id: int | None = Field(
        None, description="Server-assigned id; None until created/retrieved."
    )
    name: str = Field(description="Tag name.")
    description: str = Field("", description="Free-text description (max 500 chars).")
    auto_assign: bool = Field(
        True,
        description="If True the system may auto-assign this tag; else user-only.",
    )
    # Read-only, populated from responses.
    document_count: int | None = Field(
        None, description="Number of documents carrying this tag (read-only)."
    )
    created_at: datetime | None = Field(
        None, description="Creation timestamp (read-only)."
    )
    updated_at: datetime | None = Field(
        None, description="Last-update timestamp (read-only)."
    )

    # --- instance lifecycle ------------------------------------------------
    def create(self, client: LightOn) -> Tag:
        """Create this tag and bind the client for later lifecycle calls.

        Args:
            client: The client to create the tag with and bind to `self`.

        Returns:
            `self`, updated with the server-assigned id and read-only fields.
        """
        data = client._request(
            "POST",
            _BASE,
            json={
                "name": self.name,
                "description": self.description,
                "auto_assign": self.auto_assign,
            },
        )
        self._client = client
        return self._absorb(data)

    # The tags API exposes no single-tag GET, so these inherited reads can't work.
    @classmethod
    def get(cls, client: LightOn, id: int | str) -> NoReturn:
        raise NotImplementedError(_NO_GET)

    def refresh(self) -> NoReturn:
        raise NotImplementedError(_NO_GET)


def resolve_ids(client: LightOn, tags: _list[Tag | int | str]) -> _list[int]:
    """Coerce a mixed list of Tag objects / ids / names to tag ids.

    Names are looked up via a single ``Tag.list(client)``; a name with no matching
    tag raises ValueError so a typo fails loudly instead of silently tagging nothing.

    Args:
        client: Client used to list tags when names need resolving.
        tags: Tag objects, integer ids, and/or tag-name strings (mix freely).

    Returns:
        The resolved integer tag ids.

    Raises:
        ValueError: On an unsaved Tag (no id) or an unknown tag name.
    """
    ids: _list[int] = []
    names: _list[str] = []
    for t in tags:
        if isinstance(t, str):
            names.append(t)
        elif isinstance(t, int):
            ids.append(t)
        elif t.id is not None:
            ids.append(t.id)
        else:
            raise ValueError("cannot resolve an unsaved Tag (no id)")
    if names:
        by_name = {t.name: t.id for t in Tag.list(client) if t.id is not None}
        missing = [n for n in names if n not in by_name]
        if missing:
            raise ValueError(f"unknown tag name(s): {', '.join(missing)}")
        ids += [by_name[n] for n in names]
    return ids
