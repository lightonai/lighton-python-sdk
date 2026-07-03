"""`parse` — parse a document into per-page text (synchronous)."""

from __future__ import annotations

from pathlib import Path

from lighton.types.api import ParseResponse
from lighton.verbs._base import _VerbClient


class ParseMixin(_VerbClient):
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
