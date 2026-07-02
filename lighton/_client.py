"""Synchronous LightOn API client.

The 4 primary verbs (ask, search, parse, extract) live directly on the client.
CRUD-style groups (files, ingestion, keys) will hang off resource namespaces in
resources.py — wired in __init__ once that module lands.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from lighton import exceptions as exc
from lighton.types import LightOnConfiguration


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
    # ponytail: payloads return raw dicts for now.
    # Wrap returns in pydantic models from lighton.types.api once you curate them.
    def ask(self, **payload: Any) -> Any:
        """POST /api/v3/ask — ask a grounded question over indexed documents.

        Args:
            **payload: Request body fields (e.g. `query`, `workspace_ids`).

        Returns:
            The parsed JSON response.
        """
        return self._request("POST", "/api/v3/ask", json=payload)

    def search(self, **payload: Any) -> Any:
        """POST /api/v3/search — retrieve relevant passages (no generation).

        Args:
            **payload: Request body fields (e.g. `query`, `workspace_ids`, `file_id`).

        Returns:
            The parsed JSON response.
        """
        return self._request("POST", "/api/v3/search", json=payload)

    def parse(self, **payload: Any) -> Any:
        """POST /api/v3/parse — parse a document into per-page text.

        Args:
            **payload: Request body fields (e.g. the document and parse options).

        Returns:
            The parsed JSON response.
        """
        return self._request("POST", "/api/v3/parse", json=payload)

    def extract(self, **payload: Any) -> Any:
        """POST /api/v3/extract — extract structured data from a document.

        Args:
            **payload: Request body fields (e.g. the document and extraction schema).

        Returns:
            The parsed JSON response.
        """
        return self._request("POST", "/api/v3/extract", json=payload)
