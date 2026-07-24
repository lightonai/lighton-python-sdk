"""Batch-ingestion result schemas.

Pure data (per the `types/` rule); the behavior, concurrent upload, polling, the
background job, lives in `lighton/batch.py`. These reference `File` as a field
type, so `File` is imported at runtime (pydantic must resolve the annotation).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from lighton.file import File


class FailedIngest(BaseModel):
    """One file that didn't make it."""

    # Exception is not a pydantic type, allow it as an opaque field value.
    model_config = ConfigDict(arbitrary_types_allowed=True)

    source: Path = Field(description="The local path that failed.")
    error: Exception = Field(description="The exception that caused the failure.")
    file: File | None = Field(
        None,
        description="The uploaded File when the failure was at ingestion (not the "
        "upload itself); None if the upload failed or the path was missing.",
    )


class BatchIngest(BaseModel):
    """Terminal result of a batch: the Files that succeeded and what failed."""

    succeeded: list[File] = Field(
        default_factory=list, description="Files that succeeded."
    )
    failed: list[FailedIngest] = Field(
        default_factory=list, description="Failures, each with its cause."
    )

    @property
    def ok(self) -> bool:
        """True when nothing failed."""
        return not self.failed


class BatchProgress(BaseModel):
    """Live snapshot of a running batch (see `BatchIngestJob.progress`)."""

    total: int = Field(description="Total items requested.")
    uploaded: int = Field(description="Uploads accepted so far.")
    ingested: int = Field(
        description="Files that reached a terminal-OK status (only advances when wait=True)."
    )
    failed: int = Field(description="Failures so far.")
    done: bool = Field(description="True once the batch is terminal.")
