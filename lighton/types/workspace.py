"""Workspace-adjacent pure-data schemas.

Pure data (per the `types/` rule); the behavior lives on `Workspace` in
`lighton/workspace.py`.
"""

from __future__ import annotations

from builtins import list as _list
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RootContentType(BaseModel):
    """How many of a workspace's documents sit under one root content type."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(description="Root content-type path, e.g. legal.")
    label: str = Field(description="Human-readable label for that root.")
    count: int = Field(description="Documents classified under it, including children.")


class WorkspaceTaxonomy(BaseModel):
    """How much of a workspace is classified, and under which roots.

    The cheapest way to see classification coverage without listing files. Only
    the **list** endpoint returns it (`Workspace.list()`); the detail endpoint
    omits the key entirely, so `get()`/`refresh()` leave whatever was already
    there rather than clearing it.
    """

    model_config = ConfigDict(extra="ignore")

    classified_files_rate: float = Field(
        description="Fraction of the workspace's files that carry a content type, 0 to 1."
    )
    root_content_types: _list[RootContentType] = Field(
        default_factory=list,
        description="Per-root document counts, one entry per root content type.",
    )


class WorkspaceSync(BaseModel):
    """The external datasource a workspace imports from, when one is connected.

    None on a workspace whose documents were uploaded directly.
    """

    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(None, description="Sync configuration name.")
    datasource_type: str | None = Field(
        None, description="Kind of connected datasource (read-only)."
    )
    source_name: str | None = Field(None, description="Name of the remote source.")
    last_status: str | None = Field(None, description="Outcome of the last import run.")
    updated_at: datetime | None = Field(
        None, description="When the sync last ran; None if it never has."
    )
    next_import_date: datetime | None = Field(
        None, description="When the next import is due; None if none is scheduled."
    )
    failed_files_count: int | None = Field(
        None, description="Files the last run could not import."
    )
    editable: bool | None = Field(
        None, description="Whether the caller may change this configuration."
    )
    instance_url: str | None = Field(None, description="Remote instance URL, if any.")
    tenant_id: str | None = Field(None, description="Remote tenant identifier, if any.")
    site_name: str | None = Field(None, description="Remote site name, if any.")
    client_id: str | None = Field(None, description="Remote client identifier, if any.")
    filter_criteria: Any = Field(
        None, description="Datasource-specific import filter, passed through as-is."
    )
