"""`extract`, extract structured data from a document, guided by a JSON schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, overload

from pydantic import BaseModel

from lighton.enums import ExecMode
from lighton.job import ExtractJob
from lighton.types.api import ExtractJobResponse
from lighton.utils import _id, as_json_schema
from lighton.verbs._base import _VerbClient

if TYPE_CHECKING:
    from lighton.file import File


class ExtractMixin(_VerbClient):
    @overload
    def extract(
        self,
        schema: type[BaseModel] | dict[str, Any],
        *,
        path: str | Path | None = ...,
        url: str | None = ...,
        file: File | int | None = ...,
        options: dict[str, Any] | None = ...,
        mode: Literal[ExecMode.SYNC] = ...,
    ) -> ExtractJobResponse: ...
    @overload
    def extract(
        self,
        schema: type[BaseModel] | dict[str, Any],
        *,
        path: str | Path | None = ...,
        url: str | None = ...,
        file: File | int | None = ...,
        options: dict[str, Any] | None = ...,
        mode: Literal[ExecMode.ASYNC],
        wait: bool = ...,
        timeout: float = ...,
    ) -> ExtractJob: ...
    def extract(
        self,
        schema: type[BaseModel] | dict[str, Any],
        *,
        path: str | Path | None = None,
        url: str | None = None,
        file: File | int | None = None,
        options: dict[str, Any] | None = None,
        mode: ExecMode = ExecMode.SYNC,
        wait: bool = False,
        timeout: float = 300.0,
    ) -> ExtractJobResponse | ExtractJob:
        """POST /api/v3/extract, extract structured data from a document.

        Pass exactly one of:
            path: A local file to upload (multipart).
            url: A publicly accessible URL to fetch.
            file: An already-ingested file (File object or id), no re-upload,
                the server reads the document it already has.

        Args:
            schema: The guided-generation schema driving extraction, either a
                pydantic model class (converted to a vLLM `response_format` JSON
                Schema) or a dict already holding a valid such schema.
            options: Free-form request options; currently ``{"async": bool}``.
            mode: ExecMode.SYNC (default) runs inline and returns the extracted
                data. ExecMode.ASYNC queues the job and returns an ``ExtractJob``
                handle, call ``.poll()`` until ``.succeeded``.
            wait: Async only. Block until the job is terminal, so the returned
                ``ExtractJob`` already carries its ``result``.
            timeout: Seconds to wait when wait=True before raising TimeoutError.

        Returns:
            ``ExtractJobResponse`` (with data) when sync; an ``ExtractJob`` when
            async, pollable (wait=False) or already finished (wait=True).

        Raises:
            ValueError: If not exactly one of path/url/file is given, or wait=True
                without ExecMode.ASYNC (sync already blocks).
            TimeoutError: If wait=True and `timeout` elapses first.
            LightOnError: If wait=True and the job ends in failure.
        """
        if sum(x is not None for x in (path, url, file)) != 1:
            raise ValueError(
                "extract() requires exactly one of 'path', 'url' or 'file'"
            )
        if wait and mode != ExecMode.ASYNC:
            raise ValueError("wait=True only applies to mode=ExecMode.ASYNC")
        if mode == ExecMode.ASYNC:
            options = {**(options or {}), "async": True}
        json_schema = as_json_schema(schema)
        if path is not None:
            path = Path(path)
            # multipart: schema/options ride as JSON-encoded form fields.
            data = {"schema": json.dumps(json_schema)}
            if options is not None:
                data["options"] = json.dumps(options)
            with path.open("rb") as fh:
                resp = self._request(
                    "POST",
                    "/api/v3/extract",
                    files={"file": (path.name, fh)},
                    data=data,
                )
        else:
            source = {"document": url} if url is not None else {"file_id": _id(file)}
            body: dict[str, Any] = {**source, "schema": json_schema}
            if options is not None:
                body["options"] = options
            resp = self._request("POST", "/api/v3/extract", json=body)
        if mode == ExecMode.ASYNC:
            job = ExtractJob._bind(self, "/api/v3/extract", resp)
            return job.wait(timeout) if wait else job
        return ExtractJobResponse.model_validate(resp)
