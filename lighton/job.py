"""Async job handles for parse/extract, a client-bound object you poll() in place.

`parse(mode=ASYNC)` / `extract(mode=ASYNC)` return a `ParseJob` / `ExtractJob`
instead of a full response. Call `poll()` to re-fetch the status and update the
same object; `done`/`succeeded` read the terminal state. The two subclasses exist
only because `result` differs (`ParseResult.pages` vs `ExtractResult.data`), the
polling plumbing is shared on `_Job`.
"""

from __future__ import annotations

from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, PrivateAttr

from lighton.enums import JobStatus
from lighton.types.api import (
    ExtractDocument,
    ExtractResult,
    ExtractUsage,
    JobProgress,
    ParseDocument,
    ParseError,
    ParseResult,
    ParseUsage,
)
from lighton.verbs._base import _VerbClient


class _Job(BaseModel):
    # Responses carry extra fields the curated schema doesn't model; ignore them.
    model_config = ConfigDict(extra="ignore")

    id: str = Field(description="Async job id; poll its endpoint for status.")
    status: str = Field(
        description="Current status; compare against JobStatus (see .succeeded)."
    )
    created_at: AwareDatetime | None = Field(
        None, description="When the job was accepted."
    )
    completed_at: AwareDatetime | None = Field(
        None, description="Set once the job is terminal (success or failure)."
    )
    processing_time_ms: int | None = Field(
        None, description="Wall-clock processing time, populated once terminal."
    )
    progress: JobProgress | None = Field(
        None, description="Live progress (percentage, pages) while in flight."
    )

    # Only needs the transport (_request); LightOn supplies it. Typed as the
    # verb-client surface so binding `self` from a mixin type-checks.
    _client: _VerbClient | None = PrivateAttr(default=None)
    _path: str | None = PrivateAttr(default=None)  # e.g. "/api/v3/parse"

    @classmethod
    def _bind(cls, client: _VerbClient, path: str, data: dict) -> Self:
        obj = cls.model_validate(data)
        obj._client = client
        obj._path = path
        return obj

    def poll(self, *, page: int | None = None) -> Self:
        """Re-fetch this job's status from the API, updating this object in place.

        Args:
            page: Page of ``result.data`` to fetch (extract only, results paginate).

        Returns:
            `self`, refreshed with the latest status/result.

        Raises:
            ValueError: If the job isn't bound to a client (built by hand, not
                returned from parse/extract).
        """
        if self._client is None or self._path is None:
            raise ValueError("job is not bound to a client")
        params = {"page": page} if page is not None else None
        data = self._client._request("GET", f"{self._path}/{self.id}", params=params)
        fresh = type(self).model_validate(data)
        for field in type(self).model_fields:
            if field in data:  # only overwrite what the response returned
                setattr(self, field, getattr(fresh, field))
        return self

    @property
    def done(self) -> bool:
        """True once the job is terminal, finished, whether it succeeded or failed."""
        return self.completed_at is not None

    @property
    def succeeded(self) -> bool:
        """True once the job finished successfully (``status == completed``)."""
        return self.status == JobStatus.completed


class ParseJob(_Job):
    document: ParseDocument | None = Field(
        None, description="Parsed-document metadata, once completed."
    )
    result: ParseResult | None = Field(
        None, description="Per-page text, populated once completed."
    )
    usage: ParseUsage | None = Field(
        None, description="Pages processed, populated once completed."
    )
    error: ParseError | None = Field(
        None, description="Failure detail on a terminal-failed job, else null."
    )


class ExtractJob(_Job):
    document: ExtractDocument | None = Field(
        None, description="Source-document metadata, once completed."
    )
    result: ExtractResult | None = Field(
        None, description="Extracted data, populated once completed."
    )
    usage: ExtractUsage | None = Field(
        None, description="Pages processed, populated once completed."
    )
