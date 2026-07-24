"""`search`, retrieve relevant passages (no generation)."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from lighton.enums import RelevanceScoring, SearchMode
from lighton.tag import resolve_ids
from lighton.types.api import SearchResponse
from lighton.utils import _compact, _ids
from lighton.verbs._base import _VerbClient

if TYPE_CHECKING:
    from lighton._client import LightOn
    from lighton.file import File
    from lighton.tag import Tag
    from lighton.workspace import Workspace


class SearchMixin(_VerbClient):
    def search(
        self,
        query: str,
        *,
        workspaces: list[Workspace | int] | None = None,
        tags: list[Tag | int | str] | None = None,
        files: list[File | int] | None = None,
        max_results: int | None = None,
        mode: SearchMode | None = None,
        relevance_scoring: RelevanceScoring | None = None,
        include_image: bool | None = None,
        include_bboxes: bool | None = None,
    ) -> SearchResponse:
        """POST /api/v3/search, retrieve relevant passages (no generation).

        Args:
            query: Natural-language search query (max 1500 chars).
            workspaces: Restrict to these workspaces (Workspace objects or ids).
                Excludes files.
            tags: Restrict to documents carrying any of these tags, Tag objects,
                ids, or names (OR-matched). Names are resolved via Tag.list() and
                must exist. Excludes files.
            files: Restrict to these files (File objects or ids). Excludes
                workspaces and tags.
            max_results: Chunks to return after reranking (1–50; server default 10).
            mode: SearchMode.text (hybrid keyword+vector) or .vision (page-image).
            relevance_scoring: RelevanceScoring, .scoring_and_filtering (default),
                .scoring_only, or .none.
            include_image: Attach a base64 page image to each result.
            include_bboxes: Attach chunk bounding boxes (PDF text-mode only).

        Returns:
            The ranked search results.
        """
        tag_ids = resolve_ids(cast("LightOn", self), tags) if tags else None
        body = _compact(
            query=query,
            workspace_id=_ids(workspaces),
            tag_id=tag_ids,
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
