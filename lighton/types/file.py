"""File-adjacent pure-data schemas.

Pure data (per the `types/` rule); the behavior lives on `File` in `lighton/file.py`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExternalMetadata(BaseModel):
    """Where a document came from in a third-party system.

    How a synced document keeps its origin id: set it on upload (or with save())
    and it survives on the File, so a later sync can match the platform document
    back to the record it was ingested from.

    Updates **merge** server-side, including into `additional_metadata`: patching
    one key leaves the others in place, there is no way to drop a key this way.
    """

    # Responses carry fields the curated schema doesn't model; ignore them.
    model_config = ConfigDict(extra="ignore")

    external_id: str | None = Field(
        None,
        description="Document id in the source system; required the first time.",
    )
    doc_type: str | None = Field(
        None, description="Document type in the source system, e.g. 'incident'."
    )
    additional_metadata: Any = Field(
        None,
        description="Arbitrary JSON (url, version, timestamps...), passed through as-is.",
    )
