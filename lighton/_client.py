"""Synchronous LightOn API client.

The 4 primary verbs (ask, search, parse, extract) are mixed in from lighton/verbs/;
this module holds only the transport core (auth, _request, lifecycle). CRUD-style
groups (files, ingestion, keys) hang off the active-record resources instead.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from lighton import exceptions as exc
from lighton.types import LightOnConfiguration
from lighton.verbs import AskMixin, ExtractMixin, ParseMixin, SearchMixin


class LightOn(AskMixin, SearchMixin, ParseMixin, ExtractMixin):
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
