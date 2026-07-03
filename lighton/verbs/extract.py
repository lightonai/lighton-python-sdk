"""`extract` — extract structured data from a document."""

from __future__ import annotations

from typing import Any

from lighton.verbs._base import _VerbClient


class ExtractMixin(_VerbClient):
    def extract(self, **payload: Any) -> Any:
        """POST /api/v3/extract — extract structured data from a document.

        Args:
            **payload: Request body fields (e.g. the document and extraction schema).

        Returns:
            The parsed JSON response.
        """
        return self._request("POST", "/api/v3/extract", json=payload)
