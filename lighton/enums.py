"""Curated status/role vocabularies shared across resources.

StrEnum, not Enum: members ARE strings, so `file.status == "embedded"` and
membership in a plain-string set keep working — no `.value` needed at call sites.
Values mirror the generated api types (StatusEnum, RoleEnum); regenerate those
and update here if the server vocabulary changes.
"""

from __future__ import annotations

from enum import StrEnum


class FileStatus(StrEnum):
    """Ingestion pipeline status for a File."""

    pending = "pending"
    pending_conversion = "pending_conversion"
    converting = "converting"
    parsing = "parsing"
    parsing_failed = "parsing_failed"
    embedding = "embedding"
    embedding_failed = "embedding_failed"
    embedded = "embedded"
    parsed = "parsed"
    fail = "fail"
    updating = "updating"


class Role(StrEnum):
    """Access role granted by an API-key scope on a workspace."""

    viewer = "viewer"
    editor = "editor"
    owner = "owner"
