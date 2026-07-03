"""`search` — retrieve relevant passages (no generation)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lighton.enums import RelevanceScoring, SearchMode
from lighton.types.api import SearchResponse
from lighton.utils import _compact, _ids
from lighton.verbs._base import _VerbClient

if TYPE_CHECKING:
    from lighton.file import File
    from lighton.tag import Tag
    from lighton.workspace import Workspace


class SearchMixin(_VerbClient):
    def search(
        self,
        query: str,
        *,
        workspaces: list[Workspace | int] | None = None,
        tags: list[Tag | int] | None = None,
        files: list[File | int] | None = None,
        max_results: int | None = None,
        mode: SearchMode | None = None,
        relevance_scoring: RelevanceScoring | None = None,
        include_image: bool | None = None,
        include_bboxes: bool | None = None,
    ) -> SearchResponse:
        """POST /api/v3/search — retrieve relevant passages (no generation).

        Args:
            query: Natural-language search query (max 1500 chars).
            workspaces: Restrict to these workspaces (Workspace objects or ids).
                Excludes files.
            tags: Restrict to documents carrying any of these tags (Tag objects or
                ids; OR-matched). Excludes files.
            files: Restrict to these files (File objects or ids). Excludes
                workspaces and tags.
            max_results: Chunks to return after reranking (1–50; server default 10).
            mode: SearchMode.text (hybrid keyword+vector) or .vision (page-image).
            relevance_scoring: RelevanceScoring — .scoring_and_filtering (default),
                .scoring_only, or .none.
            include_image: Attach a base64 page image to each result.
            include_bboxes: Attach chunk bounding boxes (PDF text-mode only).

        Returns:
            The ranked search results.
        """
        body = _compact(
            query=query,
            workspace_id=_ids(workspaces),
            tag_id=_ids(tags),
            file_id=_ids(files),
            max_results=max_results,
            mode=mode,
            relevance_scoring=relevance_scoring,
            include_image=include_image,
            include_bboxes=include_bboxes,
        )
        return SearchResponse.model_validate(
            self._request("POST", "/api/v3/search", json=body)
        )
