"""`extract` — extract structured data from a document, guided by a JSON schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, overload

from pydantic import BaseModel

from lighton.enums import ExecMode
from lighton.job import ExtractJob
from lighton.types.api import ExtractJobResponse
from lighton.utils import (
    convert_pydantic_to_response_format_json,
    validate_response_format_json,
)
from lighton.verbs._base import _VerbClient


def _as_json_schema(schema: type[BaseModel] | dict[str, Any]) -> dict[str, Any]:
    """A pydantic model class → a vLLM guided-generation schema; a dict is validated.

    A dict is validated against the JSON-Schema meta-schema (raises on malformed)
    and otherwise returned untouched. A pydantic model is converted via
    `convert_pydantic_to_response_format_json`.
    """
    if isinstance(schema, dict):
        return validate_response_format_json(schema)
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return convert_pydantic_to_response_format_json(schema)
    raise TypeError("schema must be a pydantic BaseModel subclass or a dict")


class ExtractMixin(_VerbClient):
    @overload
    def extract(
        self,
        schema: type[BaseModel] | dict[str, Any],
        *,
        path: str | Path | None = ...,
        url: str | None = ...,
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
        options: dict[str, Any] | None = ...,
        mode: Literal[ExecMode.ASYNC],
    ) -> ExtractJob: ...
    def extract(
        self,
        schema: type[BaseModel] | dict[str, Any],
        *,
        path: str | Path | None = None,
        url: str | None = None,
        options: dict[str, Any] | None = None,
        mode: ExecMode = ExecMode.SYNC,
    ) -> ExtractJobResponse | ExtractJob:
        """POST /api/v3/extract — extract structured data from a document.

        Pass exactly one of:
            path: A local file to upload (multipart).
            url: A publicly accessible URL to fetch.

        Args:
            schema: The guided-generation schema driving extraction — either a
                pydantic model class (converted to a vLLM `response_format` JSON
                Schema) or a dict already holding a valid such schema.
            options: Free-form request options; currently ``{"async": bool}``.
            mode: ExecMode.SYNC (default) runs inline and returns the extracted
                data. ExecMode.ASYNC queues the job and returns an ``ExtractJob``
                handle — call ``.poll()`` until ``.succeeded``.

        Returns:
            ``ExtractJobResponse`` (with data) when sync; a pollable ``ExtractJob``
            when async.
        """
        if (path is None) == (url is None):
            raise ValueError("extract() requires exactly one of 'path' or 'url'")
        if mode == ExecMode.ASYNC:
            options = {**(options or {}), "async": True}
        json_schema = _as_json_schema(schema)
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
            body: dict[str, Any] = {"document": url, "schema": json_schema}
            if options is not None:
                body["options"] = options
            resp = self._request("POST", "/api/v3/extract", json=body)
        if mode == ExecMode.ASYNC:
            return ExtractJob._bind(self, "/api/v3/extract", resp)
        return ExtractJobResponse.model_validate(resp)
