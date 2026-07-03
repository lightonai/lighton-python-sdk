"""`ask` — grounded question answering over indexed documents."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lighton.types.api import AskResponse
from lighton.utils import _compact, _ids
from lighton.verbs._base import _VerbClient

if TYPE_CHECKING:
    from lighton.file import File
    from lighton.workspace import Workspace


class AskMixin(_VerbClient):
    # ponytail: tags, content_type, and attribute filters are deferred — add the
    # tag_id/content_type/attribute params (and streaming/async) when needed.
    def ask(
        self,
        query: str,
        *,
        workspaces: list[Workspace | int] | None = None,
        files: list[File | int] | None = None,
        max_results: int | None = None,
        model: str | None = None,
    ) -> AskResponse:
        """POST /api/v3/ask — ask a grounded question over indexed documents.

        Args:
            query: Natural-language question (max 1500 chars).
            workspaces: Restrict to these workspaces (Workspace objects or ids).
                Excludes files.
            files: Restrict to these files (File objects or ids). Excludes workspaces.
            max_results: Chunks to retrieve for context (1–50; server default 10).
            model: LLM for answer generation; platform default if omitted.

        Returns:
            The answer plus the ranked results used as context.
        """
        body = _compact(
            query=query,
            workspace_id=_ids(workspaces),
            file_id=_ids(files),
            max_results=max_results,
            model=model,
        )
        return AskResponse.model_validate(
            self._request("POST", "/api/v3/ask", json=body)
        )
