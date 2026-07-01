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

from lighton.enums import Role

if TYPE_CHECKING:
    from lighton._client import LightOn

_BASE = "/api/v3/keys"


class ApiKeyScope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    workspace_id: int = Field(description="Workspace this scope grants access to.")
    role: Role = Field(description="Access role granted on the workspace.")


class ApiKey(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = Field(
        None, description="Server-assigned id; None until created/retrieved."
    )
    name: str = Field(description="API key display name.")
    expires_at: datetime | None = Field(
        None, description="Expiry timestamp; None for no expiry."
    )
    scopes: _list[ApiKeyScope] = Field(
        default_factory=list,
        description="Per-workspace access scopes; empty for an unscoped key.",
    )
    # Read-only, populated from responses.
    prefix: str | None = Field(
        None, description="Non-secret key prefix for identification (read-only)."
    )
    created_at: datetime | None = Field(
        None, description="Creation timestamp (read-only)."
    )
    key: str | None = Field(
        None, description="Plaintext secret — returned ONLY by create(), once."
    )

    _client: LightOn | None = PrivateAttr(default=None)

    # --- class-level (no instance yet) -------------------------------------
    @classmethod
    def list(cls, client: LightOn) -> _list[ApiKey]:
        """List every API key, following pagination to the end.

        The plaintext secret is never included here — only create() returns it.

        Args:
            client: The client used to make the request and bind to each result.

        Returns:
            All API keys the caller can see, each bound to `client`.
        """
        items: _list[ApiKey] = []
        path: str | None = _BASE
        while path:  # follow pagination — no silent truncation
            page = client._request("GET", path)
            items.extend(cls._bind(client, row) for row in page["results"])
            path = page.get("next")
        return items

    @classmethod
    def get(cls, client: LightOn, id: str) -> ApiKey:
        """Fetch a single API key by id (without the plaintext secret).

        Args:
            client: The client used to make the request and bind to the result.
            id: The API key id to retrieve.

        Returns:
            The API key, bound to `client`.
        """
        return cls._bind(client, client._request("GET", f"{_BASE}/{id}"))

    # --- instance lifecycle ------------------------------------------------
    def create(self, client: LightOn) -> ApiKey:
        """Create this API key and bind the client for later lifecycle calls.

        Args:
            client: The client to create the key with and bind to `self`.

        Returns:
            `self`, updated with the id and the one-time plaintext `key`.
        """
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
        """Persist local edits to name/scopes (PATCH).

        Returns:
            `self`, refreshed with the server's response (never re-includes `key`).
        """
        data = self._api(
            "PATCH",
            f"{_BASE}/{self.id}",
            json={"name": self.name, "scopes": [s.model_dump() for s in self.scopes]},
        )
        return self._absorb(data)

    def refresh(self) -> ApiKey:
        """Re-fetch this API key from the API (GET).

        Returns:
            `self`, updated with the latest fields; the in-memory `key` is kept.
        """
        return self._absorb(self._api("GET", f"{_BASE}/{self.id}"))

    def delete(self) -> None:
        """Delete this API key and clear its local id."""
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
