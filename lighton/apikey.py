"""API key schema + management (active-record, see `_ActiveRecord`).

The plaintext secret (`key`) is returned only by create(), once. list()/get()/
save()/refresh() never resend it, create() is your only chance to read it.
"""

from __future__ import annotations

# The list() classmethod shadows builtin list in annotations (class scope).
from builtins import list as _list
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from lighton._active_record import _ActiveRecord
from lighton.enums import Role

if TYPE_CHECKING:
    from lighton._client import LightOn

_BASE = "/api/v3/keys"


class ApiKeyScope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    workspace_id: int = Field(description="Workspace this scope grants access to.")
    role: Role = Field(description="Access role granted on the workspace.")


class ApiKey(_ActiveRecord):
    _base: ClassVar[str] = _BASE
    _resource: ClassVar[str] = "api key"

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
    key: SecretStr | None = Field(
        None,
        description="Plaintext secret, returned ONLY by create(), once. Use .get_secret_value().",
    )

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
            # `or None`: empty scopes means unscoped, matching create(), not [].
            json={
                "name": self.name,
                "scopes": [s.model_dump() for s in self.scopes] or None,
            },
        )
        return self._absorb(data)
