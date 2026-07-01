"""File schema + management (active-record), mirroring Workspace/ApiKey.

Uploading a file to a workspace *is* the ingestion: POST /api/v3/files returns a
File carrying a processing `status` (pending → converting → parsing → embedding →
embedded, or a *_failed / fail terminal state). There is no separate ingestion-job
resource — you poll this same File (refresh()/wait()) until it's terminal.

create() is a multipart upload (binary `file` + form fields), unlike the JSON
create() on Workspace/ApiKey. list()/get()/delete()/save() match their shape.
"""

from __future__ import annotations

import time

# The list() classmethod shadows builtin list in annotations (class scope).
from builtins import list as _list
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from lighton.enums import FileStatus
from lighton.exceptions import LightOnError

if TYPE_CHECKING:
    from lighton._client import LightOn

_BASE = "/api/v3/files"

# Terminal ingestion states. Everything else means still in flight.
_TERMINAL_OK = {FileStatus.embedded, FileStatus.parsed}
_TERMINAL_BAD = {
    FileStatus.parsing_failed,
    FileStatus.embedding_failed,
    FileStatus.fail,
}


class File(BaseModel):
    # Response carries extra fields (workspace, summaries, content_types, …); ignore.
    model_config = ConfigDict(extra="ignore")

    id: int | None = Field(
        None, description="Server-assigned id; None until created/retrieved."
    )
    path: Path | None = Field(
        None,
        description="Local source file to upload; set before create(), never in a response.",
    )
    workspace_id: int | None = Field(
        None,
        description="Target workspace for upload; required to create (Workspace.ingest fills it).",
    )
    filename: str | None = Field(
        None, description="Document filename; defaults to path.name on upload."
    )
    title: str | None = Field(
        None, description="Document title; defaults to the filename server-side."
    )
    parser: str | None = Field(
        None, description="Ingestion pipeline to use; platform default if omitted."
    )
    # Read-only, populated from responses.
    status: FileStatus | None = Field(
        None, description="Ingestion pipeline status (read-only)."
    )
    status_detail: str | None = Field(
        None, description="Free-text error detail, present only on failure (read-only)."
    )
    extension: str | None = Field(
        None, description="File extension of the document (read-only)."
    )
    total_pages: int | None = Field(
        None, description="Total page count of the document (read-only)."
    )
    size: int | None = Field(None, description="File size in bytes (read-only).")
    created_at: datetime | None = Field(
        None, description="Creation timestamp (read-only)."
    )
    updated_at: datetime | None = Field(
        None, description="Last-update timestamp (read-only)."
    )

    _client: LightOn | None = PrivateAttr(default=None)

    # --- class-level (no instance yet) -------------------------------------
    @classmethod
    def list(cls, client: LightOn, *, workspace_id: int | None = None) -> _list[File]:
        """List files, following pagination to the end.

        Args:
            client: The client used to make the request and bind to each result.
            workspace_id: Optional filter; omit to list files across all workspaces.

        Returns:
            The matching files, each bound to `client`.
        """
        params = {"workspace_id": workspace_id} if workspace_id is not None else None
        items: _list[File] = []
        path: str | None = _BASE
        while path:  # follow pagination — no silent truncation
            page = client._request("GET", path, params=params)
            items.extend(cls._bind(client, row) for row in page["results"])
            path = page.get("next")
            params = None  # `next` already carries the query string
        return items

    @classmethod
    def get(cls, client: LightOn, id: int) -> File:
        """Fetch a single file by id.

        Args:
            client: The client used to make the request and bind to the result.
            id: The file id to retrieve.

        Returns:
            The file, bound to `client`.
        """
        return cls._bind(client, client._request("GET", f"{_BASE}/{id}"))

    # --- instance lifecycle ------------------------------------------------
    def create(self, client: LightOn, *, tags: _list[int] | None = None) -> File:
        """Upload the file (multipart) — this starts ingestion.

        Args:
            client: The client to upload with and bind to `self`.
            tags: Optional tag ids to assign to the document on upload.

        Returns:
            `self`, updated with the server-assigned id and initial status.

        Raises:
            ValueError: If `path` or `workspace_id` is not set.
        """
        if self.path is None:
            raise ValueError("File.path is required to upload")
        if self.workspace_id is None:
            raise ValueError("workspace_id is required (or use Workspace.ingest)")
        data: dict[str, object] = {
            "workspace_id": self.workspace_id,
            "filename": self.filename or self.path.name,
        }
        if self.title:
            data["title"] = self.title
        if self.parser:
            data["parser"] = self.parser
        if tags:
            data["tags"] = tags  # httpx encodes a list as repeated form fields
        with self.path.open("rb") as fh:
            resp = client._request(
                "POST", _BASE, data=data, files={"file": (self.path.name, fh)}
            )
        self._client = client
        return self._absorb(resp)

    def save(self) -> File:
        """Persist local edits to title (PATCH). filename is immutable server-side.

        Returns:
            `self`, refreshed with the server's response.
        """
        return self._absorb(
            self._api("PATCH", f"{_BASE}/{self.id}", json={"title": self.title})
        )

    def refresh(self) -> File:
        """Re-fetch this file from the API (GET) — use to poll ingestion status.

        Returns:
            `self`, updated with the latest field values (including `status`).
        """
        return self._absorb(self._api("GET", f"{_BASE}/{self.id}"))

    def delete(self) -> None:
        """Delete this file and clear its local id."""
        self._api("DELETE", f"{_BASE}/{self.id}")
        self.id = None

    def wait(self, timeout: float = 300.0, poll: float = 2.0) -> File:
        """Block (polling) until ingestion reaches a terminal state.

        ponytail: dumb poll loop — the API offers no webhook. Run in a thread
        (or use wait_all) for concurrency; the SDK stays sync.

        Args:
            timeout: Max seconds to wait before raising TimeoutError.
            poll: Seconds to sleep between status checks.

        Returns:
            `self`, once `status` is a terminal-success state (embedded/parsed).

        Raises:
            TimeoutError: If `timeout` elapses before a terminal status.
            LightOnError: If ingestion ends in a terminal-failure state.
        """
        deadline = time.monotonic() + timeout
        while self.status not in _TERMINAL_OK and self.status not in _TERMINAL_BAD:
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"file {self.id} still {self.status} after {timeout}s"
                )
            time.sleep(poll)
            self.refresh()
        if self.status in _TERMINAL_BAD:
            raise LightOnError(
                f"ingestion failed ({self.status}): {self.status_detail}"
            )
        return self

    # --- internals ---------------------------------------------------------
    def _api(self, method: str, path: str, **kwargs: object):
        if self.id is None or self._client is None:
            raise ValueError("file must be created or retrieved first")
        return self._client._request(method, path, **kwargs)

    @classmethod
    def _bind(cls, client: LightOn, data: dict) -> File:
        obj = cls.model_validate(data)
        obj._client = client
        return obj

    def _absorb(self, data: dict | None) -> File:
        """Copy returned fields onto self, keeping _client and the local path."""
        if data:
            fresh = self.model_validate(data)
            for field in type(self).model_fields:
                if field in data:  # only overwrite what the response returned
                    setattr(self, field, getattr(fresh, field))
        return self


def wait_all(files: _list[File], timeout: float = 300.0) -> _list[File]:
    """Wait for many ingestions concurrently (threads, not async — sync SDK).

    Args:
        files: The files to wait on; each is polled via File.wait.
        timeout: Max seconds to wait per file before that wait raises TimeoutError.

    Returns:
        The same files, once each has reached a terminal-success status.

    Raises:
        TimeoutError: If any file does not finish within `timeout`.
        LightOnError: If any file's ingestion ends in a terminal-failure state.
    """
    with ThreadPoolExecutor() as ex:
        return list(ex.map(lambda f: f.wait(timeout), files))
