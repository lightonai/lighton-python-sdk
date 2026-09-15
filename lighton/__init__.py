from importlib.metadata import version

from lighton._client import LightOn
from lighton.apikey import ApiKey, ApiKeyScope
from lighton.batch import BatchIngest, BatchIngestJob, BatchProgress, FailedIngest
from lighton.content_type import Attribute, ContentType, Facet, Template
from lighton.enums import (
    AttributeType,
    DownloadPurpose,
    ExecMode,
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
    "DoneEvent",
    "DownloadPurpose",
    "ExecMode",
    "ExternalMetadata",
    "ExtractJob",
    "Facet",
    "FailedIngest",
    "File",
    "FileStatus",
    "JobStatus",
    "LightOn",
    "LightOnConfiguration",
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
