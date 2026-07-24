"""`parse`, parse a document into per-page text (sync, or async job you poll)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, overload

from lighton.enums import ExecMode
from lighton.job import ParseJob
from lighton.types.api import ParseResponse
from lighton.verbs._base import _VerbClient


class ParseMixin(_VerbClient):
    @overload
    def parse(
        self,
        *,
        path: str | Path | None = ...,
        url: str | None = ...,
        mode: Literal[ExecMode.SYNC] = ...,
    ) -> ParseResponse: ...
    @overload
    def parse(
        self,
        *,
        path: str | Path | None = ...,
        url: str | None = ...,
        mode: Literal[ExecMode.ASYNC],
    ) -> ParseJob: ...
    def parse(
        self,
        *,
        path: str | Path | None = None,
        url: str | None = None,
        mode: ExecMode = ExecMode.SYNC,
    ) -> ParseResponse | ParseJob:
        """POST /api/v3/parse, parse a document into per-page text.

        Pass exactly one of:
            path: A local file to upload (multipart).
            url: A publicly accessible URL to fetch.

        Args:
            mode: ExecMode.SYNC (default) runs inline and returns the full
                ``ParseResponse``. ExecMode.ASYNC queues the job and returns a
                ``ParseJob`` handle, call ``.poll()`` until ``.succeeded``.

        Returns:
            ``ParseResponse`` when sync; a pollable ``ParseJob`` when async.
        """
        if (path is None) == (url is None):
            raise ValueError("parse() requires exactly one of 'path' or 'url'")
        is_async = mode == ExecMode.ASYNC
        options = {"async": True} if is_async else None
        if path is not None:
            path = Path(path)
            # multipart: options rides as a JSON-encoded form field.
            data = {"options": json.dumps(options)} if options else None
            with path.open("rb") as fh:
                resp = self._request(
                    "POST", "/api/v3/parse", files={"file": (path.name, fh)}, data=data
                )
        else:
            body: dict[str, Any] = {"document": url}
            if options:
                body["options"] = options
            resp = self._request("POST", "/api/v3/parse", json=body)
        if is_async:
            return ParseJob._bind(self, "/api/v3/parse", resp)
        return ParseResponse.model_validate(resp)
