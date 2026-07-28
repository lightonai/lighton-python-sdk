"""File schema + management (active-record, see `_ActiveRecord`).

Uploading a file to a workspace *is* the ingestion: POST /api/v3/files returns a
File carrying a processing `status` (pending → converting → parsing → embedding →
embedded, or a *_failed / fail terminal state). There is no separate ingestion-job
resource, you poll this same File (refresh()/wait()) until it's terminal.

create() is a multipart upload (binary `file` + form fields), unlike the JSON
create() on Workspace/ApiKey.
"""

from __future__ import annotations

import time

# The list() classmethod shadows builtin list in annotations (class scope).
from builtins import list as _list
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from pydantic import Field

from lighton._active_record import _ActiveRecord
from lighton.content_type import Facet
from lighton.enums import FileStatus
from lighton.exceptions import LightOnError
from lighton.tag import resolve_ids

if TYPE_CHECKING:
    from lighton._client import LightOn
    from lighton.content_type import ContentType
    from lighton.tag import Tag
    from lighton.workspace import Workspace

_BASE = "/api/v3/files"

# Terminal ingestion states. Everything else means still in flight.
_TERMINAL_OK = {FileStatus.embedded, FileStatus.parsed}
_TERMINAL_BAD = {
    FileStatus.parsing_failed,
    FileStatus.embedding_failed,
    FileStatus.fail,
}


class File(_ActiveRecord):
    _base: ClassVar[str] = _BASE
    _resource: ClassVar[str] = "file"

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

    # list() is inherited; filter by workspace with File.list(client, workspace_id=...).

    @classmethod
    def get_by_name(
        cls, client: LightOn, name: str, *, workspace: Workspace | int
    ) -> _list[File]:
        """Fetch every file with this user-facing name in a workspace.

        Matches `title`, not `filename`: the server uniquifies filenames on upload
        ("report.pdf" is stored as something like "report_20260728_c9be.pdf"), so the
        name you uploaded never matches the stored one. A title defaults to the
        uploaded filename without its extension, so "report.pdf" and "report" both
        find that upload.

        Titles are not unique the way stored filenames are, uploading the same
        document twice gives both copies the same title, so this returns every match
        rather than picking one. Check the length if you need exactly one.

        The API's `title` filter is a case-insensitive *partial* match, so the
        candidates it returns are narrowed to an exact title match here.

        Args:
            client: The client to query with and bind to the results.
            name: The file's title, with or without an extension (e.g. "report.pdf").
            workspace: The workspace to search in (Workspace object or id).

        Returns:
            Every File with that title, each bound to `client`; empty if none match.

        Raises:
            ValueError: If the workspace has not been created/retrieved (has no id).
        """
        workspace_id = workspace if isinstance(workspace, int) else workspace.id
        if workspace_id is None:
            raise ValueError("workspace must be created/retrieved (has no id)")
        stem = Path(name).stem  # a title defaults to the filename minus its extension
        return [
            f
            for f in cls.list(client, workspace_id=workspace_id, title=stem)
            if f.title in (name, stem)
        ]

    # --- instance lifecycle ------------------------------------------------
    def create(self, client: LightOn, *, tags: _list[int] | None = None) -> File:
        """Upload the file (multipart), this starts ingestion.

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
        if tags:
            data["tags"] = tags  # httpx encodes a list as repeated form fields
        # Read into memory (not a streamed handle): a 429 retry in _request resends
        # the same body, and a consumed handle would resend empty.
        # ponytail: whole file in RAM during its upload; stream + reopen-per-attempt
        # if you need to push files too large to buffer.
        content = self.path.read_bytes()
        resp = client._request(
            "POST", _BASE, data=data, files={"file": (self.path.name, content)}
        )
        self._client = client
        return self._absorb(resp)

    def save(self) -> File:
        """Persist local edits to title (PATCH). filename is immutable server-side.

        Returns:
            `self`, refreshed with the server's response.
        """
        # Form-encoded, not JSON: the /files endpoints accept only multipart and
        # x-www-form-urlencoded, a JSON body is rejected with 415.
        return self._absorb(
            self._api("PATCH", f"{_BASE}/{self.id}", data={"title": self.title})
        )

    def tag(self, tags: _list[Tag | int | str]) -> File:
        """Assign tags to this file (POST /files/<id>/tags).

        Args:
            tags: Tags to add, Tag objects, ids, or names (mix freely). Names are
                resolved via Tag.list() and must exist. Empty is a no-op.

        Returns:
            `self`, refreshed from the response.

        Raises:
            ValueError: If this file isn't persisted, or a name/Tag can't resolve.
        """
        ids = resolve_ids(self._bound_client(), tags)
        if not ids:
            return self
        return self._absorb(
            self._api("POST", f"{_BASE}/{self.id}/tags", json={"tags": ids})
        )

    def untag(self, tags: _list[Tag | int | str]) -> File:
        """Remove tags from this file (DELETE /files/<id>/tags/<tag_id>, one each).

        Args:
            tags: Tags to remove, Tag objects, ids, or names (mix freely). Names
                are resolved via Tag.list() and must exist. Empty is a no-op.

        Returns:
            `self`.

        Raises:
            ValueError: If this file isn't persisted, or a name/Tag can't resolve.
        """
        for tag_id in resolve_ids(self._bound_client(), tags):
            self._api("DELETE", f"{_BASE}/{self.id}/tags/{tag_id}")
        return self

    # --- content-type classification (facets) ------------------------------
    def _facet(self, action: str, content_type: ContentType | str, **extra: object):
        path = content_type if isinstance(content_type, str) else content_type.path
        return self._api(
            "POST",
            f"{_BASE}/{self.id}/facets",
            json={"action": action, "content_type_path": path, **extra},
        )

    def classify(self, content_type: ContentType | str) -> File:
        """Assign a content type to this file (ContentType object or path string).

        Args:
            content_type: The content type to assign, e.g. "legal:contract:nda".

        Returns:
            `self`.

        Raises:
            ValueError: If this file has not been created/retrieved yet.
        """
        self._facet("classify", content_type)
        return self

    def unclassify(self, content_type: ContentType | str) -> File:
        """Remove a content-type assignment from this file.

        Args:
            content_type: The content type to unassign (object or path string).

        Returns:
            `self`.
        """
        self._facet("unclassify", content_type)
        return self

    def set_attribute(
        self, content_type: ContentType | str, name: str, value: object
    ) -> File:
        """Set an attribute value under an assigned content type.

        Args:
            content_type: The assigned content type (object or path string).
            name: Attribute identifier (snake_case).
            value: The value; shape depends on the attribute type (string, number,
                date "YYYY-MM-DD", bool, or list[str] for multi-select).

        Returns:
            `self`.
        """
        self._facet("set_value", content_type, attribute_name=name, value=value)
        return self

    def clear_attribute(self, content_type: ContentType | str, name: str) -> File:
        """Clear an attribute value under an assigned content type.

        Args:
            content_type: The assigned content type (object or path string).
            name: Attribute identifier to clear.

        Returns:
            `self`.
        """
        self._facet("clear_value", content_type, attribute_name=name)
        return self

    def facets(self) -> _list[Facet]:
        """List this file's assigned content types and their attribute values.

        Returns:
            One Facet per assigned content type (with its attribute values).

        Raises:
            ValueError: If this file has not been created/retrieved yet.
        """
        data = self._api("GET", f"{_BASE}/{self.id}/facets")
        return [Facet.model_validate(ct) for ct in data.get("content_types", [])]

    def wait(self, timeout: float = 300.0, poll: float = 2.0) -> File:
        """Block (polling) until ingestion reaches a terminal state.

        ponytail: dumb poll loop, the API offers no webhook. Run in a thread
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


def wait_all(files: _list[File], timeout: float = 300.0) -> _list[File]:
    """Wait for many ingestions concurrently (threads, not async, sync SDK).

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
