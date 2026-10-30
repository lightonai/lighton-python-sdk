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


class SyncWalk(BaseModel):
    """How far an SMB directory walk has got.

    SMB has no changes API, so a sync walks the share in batches that each report
    success: `last_status` reads "success" throughout a first scan that takes
    days. `complete` is what tells a finished walk apart.
    """

    model_config = ConfigDict(extra="ignore")

    complete: bool = Field(description="False while directories are left to visit.")
    started_at: datetime | None = Field(
        None,
        description="When the walk in progress began; None before its first batch.",
    )
    pending_directories: int = Field(
        0, description="Directories queued and not yet visited; 0 once complete."
    )
    files_seen: int = Field(
        0, description="Files this walk has processed so far (not the workspace total)."
    )
    bytes_read: int = Field(0, description="Bytes pulled off the share so far.")
    failed_files: int = Field(
        0,
        description="Files of the last session that failed, files only. Prefer it "
        "over `WorkspaceSync.failed_files_count`, which also counts refused directories.",
    )
    refused_directories_count: int = Field(
        0,
        description="Directories the walk could not enter (unreadable, junction, "
        "loop, too deep); their files are absent and only the share admin can fix it.",
    )
    refused_directories: _list[str] = Field(
        default_factory=list,
        description="Up to 10 of those directories, share-relative: a sample.",
    )
    refusals_incomplete: bool = Field(
        False,
        description="True once the walk ran out of room to record what it skipped; "
        "deletion detection is then off for this import.",
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
        None,
        description="Errors on the last import session, session-level notes "
        "included; for SMB, `walk.failed_files` is the files-only figure.",
    )
    pending_files_count: int | None = Field(
        None, description="Files still waiting to be imported."
    )
    credentials_rejected: bool | None = Field(
        None,
        description="True when the source refused the credentials: syncing has "
        "stopped and won't retry until the credentials are replaced.",
    )
    editable: bool | None = Field(
        None, description="Whether the caller may change this configuration."
    )
    instance_url: str | None = Field(None, description="Remote instance URL, if any.")
    tenant_id: str | None = Field(None, description="Remote tenant identifier, if any.")
    site_name: str | None = Field(None, description="Remote site name, if any.")
    client_id: str | None = Field(None, description="Remote client identifier, if any.")
    username: str | None = Field(
        None,
        description="Account name (SMB, ServiceNow); empty where the type has none.",
    )
    auth_protocol: str | None = Field(
        None, description="SMB only: negotiate, ntlm or kerberos; empty otherwise."
    )
    kerberos_realm: str | None = Field(
        None, description="SMB only: the Kerberos realm."
    )
    kerberos_kdcs: str | None = Field(
        None, description="SMB only: the realm's KDCs, comma-separated."
    )
    connect_address: str | None = Field(
        None,
        description="SMB only: address connected to when the server name in "
        "`instance_url` doesn't resolve.",
    )
    walk: SyncWalk | None = Field(
        None, description="Directory-walk progress; SMB only, None otherwise."
    )
    filter_criteria: Any = Field(
        None, description="Datasource-specific import filter, passed through as-is."
    )


class WorkspacePermissions(BaseModel):
    """What the caller may do on a workspace, a scoped API key's limits included.

    Only the **detail** endpoint returns it (`get()`/`refresh()`), the mirror of
    `taxonomy`: `list()` leaves it None.
    """

    model_config = ConfigDict(extra="ignore")

    can_upload_files: bool = Field(
        description="May upload files; always False on a synced workspace."
    )
    can_delete_files: bool = Field(
        description="May delete files; always False on a synced workspace."
    )
    can_edit_workspace: bool = Field(description="May update name and description.")
    can_edit_datasource: bool = Field(
        description="May edit the datasource; False once a sync has succeeded "
        "(the configuration is then locked) or when there is none."
    )
    can_operate_datasource: bool = Field(
        description="May replace the datasource's credentials or pause/resume it; "
        "unlike `can_edit_datasource`, survives the post-sync lock."
    )
    can_delete_workspace: bool = Field(description="May delete the workspace.")
    can_manage_members: bool = Field(
        description="May list, add and remove workspace members."
    )
