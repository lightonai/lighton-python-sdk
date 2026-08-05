"""`ask`, grounded question answering over indexed documents."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel

from lighton.enums import RelevanceScoring
from lighton.tag import resolve_ids
from lighton.types.api import AskResponse
from lighton.utils import _compact, _ids, as_json_schema
from lighton.verbs._base import _VerbClient

if TYPE_CHECKING:
    from lighton._client import LightOn
    from lighton.file import File
    from lighton.tag import Tag
    from lighton.workspace import Workspace


class AskMixin(_VerbClient):
    # ponytail: content_type and attribute filters are deferred, add the
    # content_type/attribute params (and streaming/async) when needed.
    def ask(
        self,
        query: str,
        *,
        workspaces: list[Workspace | int] | None = None,
        tags: list[Tag | int | str] | None = None,
        files: list[File | int] | None = None,
        max_results: int | None = None,
        relevance_scoring: RelevanceScoring | None = None,
        model: str | None = None,
        schema: type[BaseModel] | dict[str, Any] | None = None,
    ) -> AskResponse:
        """POST /api/v3/ask, ask a grounded question over indexed documents.

        Args:
            query: Natural-language question (max 1500 chars).
            workspaces: Restrict to these workspaces (Workspace objects or ids).
                Excludes files.
            tags: Restrict to documents carrying any of these tags, Tag objects,
                ids, or names (OR-matched). Names are resolved via Tag.list() and
                must exist. Excludes files.
            files: Restrict to these files (File objects or ids). Excludes
                workspaces and tags.
            max_results: Chunks to retrieve for context (1–50; server default 10).
            relevance_scoring: RelevanceScoring, .scoring_and_filtering (default),
                .scoring_only, or .none.
            model: LLM for answer generation; platform default if omitted.
            schema: Constrain the answer to structured output, a pydantic model
                class or a JSON-Schema dict (same inputs as `extract`, sent as
                the API's `response_format`; must describe an object). The answer
                then comes back as JSON *text* in `.answer`, parse it with
                `YourModel.model_validate_json(resp.answer)`.

        Returns:
            The answer plus the ranked results used as context.
        """
        tag_ids = resolve_ids(cast("LightOn", self), tags) if tags else None
        body = _compact(
            query=query,
            workspace_id=_ids(workspaces),
            tag_id=tag_ids,
            file_id=_ids(files),
            max_results=max_results,
            relevance_scoring=relevance_scoring,
            model=model,
            response_format=as_json_schema(schema) if schema is not None else None,
        )
        return AskResponse.model_validate(
            self._request("POST", "/api/v3/ask", json=body)
        )
