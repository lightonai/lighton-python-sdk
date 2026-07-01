"""Workspace schema + management, independent of the auto-generated api types.

Active-record style: a Workspace instance manages its own lifecycle. create()
binds a client to the instance; subsequent save()/refresh()/delete() reuse it.
list()/get() are classmethods since there's no instance to act on yet.
"""

from __future__ import annotations

# The list() classmethod shadows builtin list in return annotations (class scope).
from builtins import list as _list
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, PrivateAttr

if TYPE_CHECKING:
    from lighton._client import LightOn
    from lighton.file import File

_BASE = "/api/v3/workspaces"


class Workspace(BaseModel):
    # Response carries extra fields (summaries, sync, scoped_api_keys); ignore them.
    model_config = ConfigDict(extra="ignore")

    id: int | None = None  # None until created/retrieved
    name: str
    description: str = ""
    # Read-only, populated from responses.
    workspace_type: str | None = None
    document_upload_method: str | None = None
    files_count: int | None = None
    used_storage: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    _client: LightOn | None = PrivateAttr(default=None)

    # --- class-level (no instance yet) -------------------------------------
    @classmethod
    def list(cls, client: LightOn) -> _list[Workspace]:
        items: list[Workspace] = []
        path: str | None = _BASE
        while path:  # follow pagination — no silent truncation
            page = client._request("GET", path)
            items.extend(cls._bind(client, row) for row in page["results"])
            path = page.get("next")
        return items

    @classmethod
    def get(cls, client: LightOn, id: int) -> Workspace:
        return cls._bind(client, client._request("GET", f"{_BASE}/{id}"))

    # --- instance lifecycle ------------------------------------------------
    def create(self, client: LightOn) -> Workspace:
        data = client._request(
            "POST", _BASE, json={"name": self.name, "description": self.description}
        )
        self._client = client
        return self._absorb(data)

    def save(self) -> Workspace:
        """Persist local edits to name/description (PATCH)."""
        data = self._api(
            "PATCH",
            f"{_BASE}/{self.id}",
            json={
                "name": self.name,
                "description": self.description,
            },
        )
        return self._absorb(data)

    def ingest(
        self,
        file: File,
        *,
        wait: bool = False,
        timeout: float = 300.0,
        tags: _list[int] | None = None,
    ) -> File:
        """Upload a File into this workspace and return it. Non-blocking by default;
        the returned File is 'pending' — refresh()/wait() to track ingestion."""
        if self.id is None or self._client is None:
            raise ValueError("workspace must be created or retrieved first")
        file.workspace_id = self.id
        created = file.create(self._client, tags=tags)
        return created.wait(timeout) if wait else created

    def refresh(self) -> Workspace:
        return self._absorb(self._api("GET", f"{_BASE}/{self.id}"))

    def delete(self) -> None:
        self._api("DELETE", f"{_BASE}/{self.id}")
        self.id = None

    # --- internals ---------------------------------------------------------
    def _api(self, method: str, path: str, **kwargs: object):
        if self.id is None or self._client is None:
            raise ValueError("workspace must be created or retrieved first")
        return self._client._request(method, path, **kwargs)

    @classmethod
    def _bind(cls, client: LightOn, data: dict) -> Workspace:
        ws = cls.model_validate(data)
        ws._client = client
        return ws

    def _absorb(self, data: dict | None) -> Workspace:
        """Copy fresh field values from a response onto self, keeping _client."""
        if data:
            fresh = self.model_validate(data)
            for field in type(self).model_fields:
                setattr(self, field, getattr(fresh, field))
        return self
