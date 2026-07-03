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


class JobStatus(StrEnum):
    """Status of an async parse/extract job.

    Only ``pending`` (initial) and ``completed`` (success) are documented by the
    API — the schema types ``status`` as a bare string with no enum and doesn't
    publish the failure vocabulary. This enum is for call-site comparisons
    (StrEnum members equal their string values), NOT to validate the response
    field, so an unrecognized server value compares unequal rather than erroring.
    Detect terminal-failure via ``completed_at`` being set without ``completed``
    (or, for parse, the ``error`` block) rather than a status string.
    """

    pending = "pending"
    completed = "completed"


class ExecMode(StrEnum):
    """Execution mode for parse/extract: run inline or queue as an async job.

    Uppercase members (unlike the other enums here) so the async member can be
    ``ASYNC`` — lowercase ``async`` is a Python keyword and can't be a member name.
    """

    SYNC = "sync"
    ASYNC = "async"


class SearchMode(StrEnum):
    """Retrieval mode for search/ask."""

    text = "text"  # hybrid keyword + vector
    vision = "vision"  # VLM-embedded page image


class RelevanceScoring(StrEnum):
    """Cross-encoder relevance scoring step for search."""

    none = "none"  # skip scoring, return all candidates
    scoring_only = "scoring_only"  # score but don't filter
    scoring_and_filtering = "scoring_and_filtering"  # score and drop below threshold


class Role(StrEnum):
    """Access role granted by an API-key scope on a workspace."""

    viewer = "viewer"
    editor = "editor"
    owner = "owner"
