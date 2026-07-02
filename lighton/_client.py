"""Synchronous LightOn API client.

The 4 primary verbs (ask, search, parse, extract) live directly on the client.
CRUD-style groups (files, ingestion, keys) will hang off resource namespaces in
resources.py — wired in __init__ once that module lands.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from lighton import exceptions as exc
from lighton.enums import RelevanceScoring, SearchMode
from lighton.types import LightOnConfiguration
from lighton.types.api import AskResponse, ParseResponse, SearchResponse

if TYPE_CHECKING:
    from lighton.file import File
    from lighton.workspace import Workspace


def _compact(**kw: Any) -> dict[str, Any]:
    """Request body from kwargs, dropping None so the server applies its defaults."""
    return {k: v for k, v in kw.items() if v is not None}


def _ids(items: list[int] | list[Any] | None) -> list[int] | None:
    """Coerce a list of resources or ints to a list of ids (duck-typed on `.id`)."""
    if items is None:
        return None
    return [x if isinstance(x, int) else x.id for x in items]


class LightOn:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        config: LightOnConfiguration | None = None,
    ) -> None:
        api_key = api_key or os.environ.get("LIGHTON_API_KEY")
        if not api_key:
            raise ValueError(
                "api_key is required (pass api_key= or set LIGHTON_API_KEY)"
            )
        config = config or LightOnConfiguration()
        # httpx.HTTPTransport(retries=) retries with exponential backoff.
        # ponytail: connection errors only, not 5xx/429. Add status retries if the API needs it.
        transport = config.transport or httpx.HTTPTransport(retries=config.retries)
        self._http = httpx.Client(
            base_url=config.base_url.rstrip("/"),
            timeout=config.timeout,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
        )

    # --- lifecycle ---------------------------------------------------------
    def __enter__(self) -> "LightOn":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    # --- transport ---------------------------------------------------------
    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Send a request, raise on error, return parsed JSON (or None for empty 2xx)."""
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.TransportError as e:
            raise exc.LightOnConnectionError(str(e)) from e
        if not response.is_success:
            raise exc.from_response(response)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as e:
            raise exc.MalformedResponseError(
                f"expected JSON but got: {response.text[:200]!r}"
            ) from e

    # --- primary verbs -----------------------------------------------------
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

    def search(
        self,
        query: str,
        *,
        workspaces: list[Workspace | int] | None = None,
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
            files: Restrict to these files (File objects or ids). Excludes workspaces.
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

    def parse(
        self, *, path: str | Path | None = None, url: str | None = None
    ) -> ParseResponse:
        """POST /api/v3/parse — parse a document into per-page text (synchronous).

        Pass exactly one of:
            path: A local file to upload (multipart).
            url: A publicly accessible URL to fetch.

        Returns:
            The parsed document (per-page text and usage).
        """
        if (path is None) == (url is None):
            raise ValueError("parse() requires exactly one of 'path' or 'url'")
        # ponytail: sync only. Add options={"async": true} + a poll loop if large
        # documents start timing out.
        if path is not None:
            path = Path(path)
            with path.open("rb") as fh:
                data = self._request(
                    "POST", "/api/v3/parse", files={"file": (path.name, fh)}
                )
        else:
            data = self._request("POST", "/api/v3/parse", json={"document": url})
        return ParseResponse.model_validate(data)

    def extract(self, **payload: Any) -> Any:
        """POST /api/v3/extract — extract structured data from a document.

        Args:
            **payload: Request body fields (e.g. the document and extraction schema).

        Returns:
            The parsed JSON response.
        """
        return self._request("POST", "/api/v3/extract", json=payload)
