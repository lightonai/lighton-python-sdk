"""Workspace schema + management, independent of the auto-generated api types.

Active-record style (see `_ActiveRecord`): a Workspace instance manages its own
lifecycle. create() binds a client to the instance; subsequent save()/refresh()/
delete() reuse it. list()/get() are inherited classmethods.
"""

from __future__ import annotations

# The list() classmethod shadows builtin list in return annotations (class scope).
from builtins import list as _list
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from pydantic import Field

from lighton._active_record import _ActiveRecord

if TYPE_CHECKING:
    from lighton._client import LightOn
    from lighton.file import File

_BASE = "/api/v3/workspaces"


class Workspace(_ActiveRecord):
    _base: ClassVar[str] = _BASE
    _resource: ClassVar[str] = "workspace"

    id: int | None = Field(
        None, description="Server-assigned id; None until created/retrieved."
    )
    name: str = Field(description="Workspace display name.")
    description: str = Field("", description="Free-text workspace description.")
    # Read-only, populated from responses.
    workspace_type: str | None = Field(None, description="Workspace type (read-only).")
    document_upload_method: str | None = Field(
        None, description="How documents are uploaded to this workspace (read-only)."
    )
    files_count: int | None = Field(
        None, description="Number of files in the workspace (read-only)."
    )
    used_storage: float | None = Field(
        None, description="Bytes of storage used (read-only)."
    )
    created_at: datetime | None = Field(
        None, description="Creation timestamp (read-only)."
    )
    updated_at: datetime | None = Field(
        None, description="Last-update timestamp (read-only)."
    )

    # --- instance lifecycle ------------------------------------------------
    def create(self, client: LightOn) -> Workspace:
        """Create this workspace and bind the client for later lifecycle calls.

        Args:
            client: The client to create the workspace with and bind to `self`.

        Returns:
            `self`, updated with the server-assigned id and read-only fields.
        """
        data = client._request(
            "POST", _BASE, json={"name": self.name, "description": self.description}
        )
        self._client = client
        return self._absorb(data)

    def save(self) -> Workspace:
        """Persist local edits to name/description (PATCH).

        Returns:
            `self`, refreshed with the server's response.
        """
        data = self._api(
            "PATCH",
            f"{_BASE}/{self.id}",
            json={"name": self.name, "description": self.description},
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
        """Upload a File into this workspace — uploading is the ingestion.

        Non-blocking by default: the returned File is 'pending', poll it via
        refresh()/wait(). Pass wait=True to block until ingestion is terminal.

        Args:
            file: The File to upload; its workspace_id is set to this workspace.
            wait: If True, block until ingestion reaches a terminal status.
            timeout: Seconds to wait when wait=True before raising TimeoutError.
            tags: Optional tag ids to assign to the document on upload.

        Returns:
            The created File, bound to this workspace's client.

        Raises:
            ValueError: If this workspace has not been created/retrieved yet.
        """
        client = self._bound_client()
        file.workspace_id = self.id
        created = file.create(client, tags=tags)
        return created.wait(timeout) if wait else created
