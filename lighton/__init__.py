from importlib.metadata import version

from lighton._client import LightOn
from lighton.apikey import ApiKey, ApiKeyScope
from lighton.batch import BatchIngest, BatchIngestJob, BatchProgress, FailedIngest
from lighton.content_type import (
    MAX_CONTENT_TYPE_ACTIONS,
    MAX_FACET_ACTIONS,
    Attribute,
    ContentType,
    ContentTypeAction,
    ContentTypeResult,
    Facet,
    FacetAction,
    FacetResult,
    Template,
)
from lighton.enums import (
    AttributeType,
    ContentTypeActionType,
    DownloadPurpose,
    ExecMode,
    FacetActionType,
    FileStatus,
    JobStatus,
    RelevanceScoring,
    ReprocessLevel,
    Role,
    SearchMode,
    ThumbnailStatus,
)
from lighton.file import File, wait_all
from lighton.job import ExtractJob, ParseJob
from lighton.tag import Tag
from lighton.types.events import (
    AskEvent,
    DoneEvent,
    SourcesEvent,
    TokenEvent,
)
from lighton.types import (
    ExternalMetadata,
    LightOnConfiguration,
    RootContentType,
    Thumbnail,
    WorkspaceSync,
    WorkspaceTaxonomy,
)
from lighton.workspace import Workspace

__version__ = version(
    "lighton-sdk"
)  # single source of truth: pyproject.toml (via installed metadata)
__all__ = [
    "ApiKey",
    "ApiKeyScope",
    "AskEvent",
    "Attribute",
    "AttributeType",
    "BatchIngest",
    "BatchIngestJob",
    "BatchProgress",
    "ContentType",
    "ContentTypeAction",
    "ContentTypeActionType",
    "ContentTypeResult",
    "DoneEvent",
    "DownloadPurpose",
    "ExecMode",
    "ExternalMetadata",
    "ExtractJob",
    "Facet",
    "FacetAction",
    "FacetActionType",
    "FacetResult",
    "FailedIngest",
    "File",
    "FileStatus",
    "JobStatus",
    "LightOn",
    "LightOnConfiguration",
    "MAX_CONTENT_TYPE_ACTIONS",
    "MAX_FACET_ACTIONS",
    "ParseJob",
    "RelevanceScoring",
    "ReprocessLevel",
    "Role",
    "RootContentType",
    "SearchMode",
    "SourcesEvent",
    "Tag",
    "Template",
    "Thumbnail",
    "TokenEvent",
    "ThumbnailStatus",
    "Workspace",
    "WorkspaceSync",
    "WorkspaceTaxonomy",
    "wait_all",
]
