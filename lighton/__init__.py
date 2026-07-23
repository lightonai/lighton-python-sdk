from importlib.metadata import version

from lighton._client import LightOn
from lighton.apikey import ApiKey, ApiKeyScope
from lighton.content_type import Attribute, ContentType, Facet
from lighton.enums import (
    ExecMode,
    FileStatus,
    JobStatus,
    RelevanceScoring,
    Role,
    SearchMode,
)
from lighton.file import File, wait_all
from lighton.job import ExtractJob, ParseJob
from lighton.tag import Tag
from lighton.types import LightOnConfiguration
from lighton.workspace import Workspace

__version__ = version(
    "lighton"
)  # single source of truth: pyproject.toml (via installed metadata)
__all__ = [
    "ApiKey",
    "ApiKeyScope",
    "Attribute",
    "ContentType",
    "ExecMode",
    "ExtractJob",
    "Facet",
    "File",
    "FileStatus",
    "JobStatus",
    "LightOn",
    "LightOnConfiguration",
    "ParseJob",
    "RelevanceScoring",
    "Role",
    "SearchMode",
    "Tag",
    "Workspace",
    "wait_all",
]
