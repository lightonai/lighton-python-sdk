"""API key schema + management (active-record), mirroring Workspace.

The plaintext secret (`key`) is returned only by create(), once. list()/get()/
save()/refresh() never resend it — create() is your only chance to read it.
"""

from __future__ import annotations

# The list() classmethod shadows builtin list in annotations (class scope).
from builtins import list as _list
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

if TYPE_CHECKING:
    from lighton._client import LightOn

_BASE = "/api/v3/keys"


class ApiKeyScope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    workspace_id: int
    role: str  # "viewer" | "editor" | "owner"


class ApiKey(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None  # None until created/retrieved
    name: str
    expires_at: datetime | None = None
    scopes: _list[ApiKeyScope] = Field(default_factory=list)
    # Read-only, populated from responses.
    prefix: str | None = None
    created_at: datetime | None = None
    key: str | None = None  # plaintext secret — returned ONLY by create(), once

    _client: LightOn | None = PrivateAttr(default=None)

    # --- class-level (no instance yet) -------------------------------------
    @classmethod
    def list(cls, client: LightOn) -> _list[ApiKey]:
        items: _list[ApiKey] = []
        path: str | None = _BASE
        while path:  # follow pagination — no silent truncation
            page = client._request("GET", path)
            items.extend(cls._bind(client, row) for row in page["results"])
            path = page.get("next")
        return items

    @classmethod
    def get(cls, client: LightOn, id: str) -> ApiKey:
        return cls._bind(client, client._request("GET", f"{_BASE}/{id}"))

    # --- instance lifecycle ------------------------------------------------
    def create(self, client: LightOn) -> ApiKey:
        payload = {
            "name": self.name,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            # Providing scopes marks the key workspace-scoped; omit when empty.
            "scopes": [s.model_dump() for s in self.scopes] or None,
        }
        data = client._request("POST", _BASE, json=payload)
        self._client = client
        return self._absorb(data)

    def save(self) -> ApiKey:
        """Persist local edits to name/scopes (PATCH)."""
        data = self._api(
            "PATCH",
            f"{_BASE}/{self.id}",
            json={"name": self.name, "scopes": [s.model_dump() for s in self.scopes]},
        )
        return self._absorb(data)

    def refresh(self) -> ApiKey:
        return self._absorb(self._api("GET", f"{_BASE}/{self.id}"))

    def delete(self) -> None:
        self._api("DELETE", f"{_BASE}/{self.id}")
        self.id = None

    # --- internals ---------------------------------------------------------
    def _api(self, method: str, path: str, **kwargs: object):
        if self.id is None or self._client is None:
            raise ValueError("api key must be created or retrieved first")
        return self._client._request(method, path, **kwargs)

    @classmethod
    def _bind(cls, client: LightOn, data: dict) -> ApiKey:
        obj = cls.model_validate(data)
        obj._client = client
        return obj

    def _absorb(self, data: dict | None) -> ApiKey:
        """Copy returned fields onto self, keeping _client and the one-time key."""
        if data:
            fresh = self.model_validate(data)
            for field in type(self).model_fields:
                if field in data:  # only overwrite what the response actually returned
                    setattr(self, field, getattr(fresh, field))
        return self
