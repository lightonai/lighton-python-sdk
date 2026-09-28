"""`search`, retrieve relevant passages (no generation)."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from lighton.content_type import ContentTypeRef, FacetScope, resolve_scope
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
        content_type: list[ContentTypeRef] | None = None,
        attribute: list[str] | None = None,
        scope: FacetScope | bool = False,
        max_results: int | None = None,
        mode: SearchMode | None = None,
        relevance_scoring: RelevanceScoring | None = None,
        include_image: bool | None = None,
        include_bboxes: bool | None = None,
    ) -> SearchResponse:
        """POST /api/v3/search, retrieve relevant passages (no generation).

        Args:
            query: Natural-language search query (max 4000 chars).
            workspaces: Restrict to these workspaces (Workspace objects or ids).
                Excludes files.
            tags: Restrict to documents carrying any of these tags, Tag objects,
                ids, or names (OR-matched). Names are resolved via Tag.list() and
                must exist. Excludes files.
            files: Restrict to these files (File objects or ids). Excludes
                workspaces and tags.
            content_type: Restrict to these content types (nodes, scored hits
                from `scope()`, or path strings; OR-matched, exact-or-subtree,
                e.g. "legal" also matches "legal:contract"; wildcards
                `legal:contract*`, `*nda*`).
            attribute: Restrict by attribute value, e.g.
                `["fiscal_year:2024|2025", "status:active"]`. Entries are ANDed,
                `|` ORs within one entry. Also `name` (has any value),
                `name:>value`, `name:prefix*`, `name:*text*`.
            scope: Derive `content_type`/`attribute` from the query instead of
                naming them. True resolves a scope from this query (one extra
                request, no LLM) and narrows by every content type it scores, up
                to the endpoint's default 20, so it is a loose net; pass a
                `ContentType.scope(..., max_results=3)` to narrow harder. A
                `FacetScope` from `ContentType.scope(..., model=...)` is applied
                as-is, attribute filters included. Refuses to combine with an
                explicit `content_type`/`attribute`.
            max_results: Chunks to return after reranking (1–100; server default 10).
            mode: SearchMode.text (hybrid keyword+vector) or .vision (page-image).
            relevance_scoring: RelevanceScoring, .scoring_and_filtering (default),
                .scoring_only, or .none.
            include_image: Attach a base64 page image to each result.
            include_bboxes: Attach chunk bounding boxes (PDF text-mode only).

        Returns:
            The ranked search results.

        Raises:
            ValueError: If `scope` is combined with `content_type`/`attribute`.
        """
        tag_ids = resolve_ids(cast("LightOn", self), tags) if tags else None
        content_type_paths, attribute = resolve_scope(
            cast("LightOn", self), query, scope, content_type, attribute
        )
        body = _compact(
            query=query,
            workspace_id=_ids(workspaces),
            tag_id=tag_ids,
            file_id=_ids(files),
            content_type=content_type_paths,
            attribute=attribute,
            max_results=max_results,
            mode=mode,
            relevance_scoring=relevance_scoring,
            include_image=include_image,
            include_bboxes=include_bboxes,
        )
        return SearchResponse.model_validate(
            self._request("POST", "/api/v3/search", json=body)
        )
