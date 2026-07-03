"""`extract` — extract structured data from a document, guided by a JSON schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

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
    def extract(
        self,
        schema: type[BaseModel] | dict[str, Any],
        *,
        path: str | Path | None = None,
        url: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> ExtractJobResponse:
        """POST /api/v3/extract — extract structured data from a document.

        Pass exactly one of:
            path: A local file to upload (multipart).
            url: A publicly accessible URL to fetch.

        Args:
            schema: The guided-generation schema driving extraction — either a
                pydantic model class (converted to a vLLM `response_format` JSON
                Schema) or a dict already holding a valid such schema.
            options: Free-form request options; currently ``{"async": bool}``.

        Returns:
            The extracted data plus document metadata and usage.
        """
        if (path is None) == (url is None):
            raise ValueError("extract() requires exactly one of 'path' or 'url'")
        json_schema = _as_json_schema(schema)
        # ponytail: sync only. Add options={"async": true} + a poll loop if large
        # documents start timing out.
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
        return ExtractJobResponse.model_validate(resp)
