"""`ask`, grounded question answering over indexed documents."""

from __future__ import annotations

import json
from collections.abc import Generator, Iterator
from typing import TYPE_CHECKING, Any, Literal, cast, overload

from pydantic import BaseModel

from lighton.enums import RelevanceScoring
from lighton.exceptions import StreamError
from lighton.tag import resolve_ids
from lighton.types.api import AskResponse
from lighton.types.events import AskEvent, DoneEvent, SourcesEvent, TokenEvent
from lighton.utils import _compact, _ids, _paths, as_json_schema
from lighton.verbs._base import _VerbClient

if TYPE_CHECKING:
    from lighton._client import LightOn
    from lighton.content_type import ContentType
    from lighton.file import File
    from lighton.tag import Tag
    from lighton.workspace import Workspace


_EVENTS: dict[str, type[AskEvent]] = {
    "sources": SourcesEvent,
    "token": TokenEvent,
    "done": DoneEvent,
}


def _sse(lines: Iterator[str]) -> Iterator[tuple[str, str]]:
    """Parse an SSE byte stream into `(event, data)` pairs.

    Handles what the spec requires of a consumer here: `event:`/`data:` fields,
    an optional single leading space after the colon, `data:` lines accumulating
    across a multi-line payload, a blank line dispatching the event, and `:`
    comment lines (heartbeats) ignored. Unknown fields are skipped, and a block
    with no `event:` defaults to "message", as the spec says.

    ponytail: no `id:`/`retry:` handling and no reconnection, because this stream
    is one-shot and the API sends neither. Add them if resumable streams appear.
    """
    event, data = "", []
    for line in lines:
        if not line:  # blank line dispatches whatever has accumulated
            if data:
                yield event or "message", "\n".join(data)
            event, data = "", []
        elif line.startswith(":"):
            continue  # comment / heartbeat
        elif ":" in line:
            field, _, value = line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            if field == "event":
                event = value
            elif field == "data":
                data.append(value)
    if data:  # a stream that ended without a trailing blank line
        yield event or "message", "\n".join(data)


class AskMixin(_VerbClient):
    # ponytail: an async client is still deferred, add it when a real event-loop
    # caller needs one.
    @overload
    def ask(
        self,
        query: str,
        *,
        workspaces: list[Workspace | int] | None = ...,
        tags: list[Tag | int | str] | None = ...,
        files: list[File | int] | None = ...,
        content_type: list[ContentType | str] | None = ...,
        attribute: list[str] | None = ...,
        max_results: int | None = ...,
        relevance_scoring: RelevanceScoring | None = ...,
        model: str | None = ...,
        schema: type[BaseModel] | dict[str, Any] | None = ...,
        stream: Literal[False] = ...,
    ) -> AskResponse: ...
    @overload
    def ask(
        self,
        query: str,
        *,
        workspaces: list[Workspace | int] | None = ...,
        tags: list[Tag | int | str] | None = ...,
        files: list[File | int] | None = ...,
        content_type: list[ContentType | str] | None = ...,
        attribute: list[str] | None = ...,
        max_results: int | None = ...,
        relevance_scoring: RelevanceScoring | None = ...,
        model: str | None = ...,
        schema: type[BaseModel] | dict[str, Any] | None = ...,
        stream: Literal[True],
    ) -> Generator[AskEvent, None, None]: ...
    def ask(
        self,
        query: str,
        *,
        workspaces: list[Workspace | int] | None = None,
        tags: list[Tag | int | str] | None = None,
        files: list[File | int] | None = None,
        content_type: list[ContentType | str] | None = None,
        attribute: list[str] | None = None,
        max_results: int | None = None,
        relevance_scoring: RelevanceScoring | None = None,
        model: str | None = None,
        schema: type[BaseModel] | dict[str, Any] | None = None,
        stream: bool = False,
    ) -> AskResponse | Generator[AskEvent, None, None]:
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
            content_type: Restrict to these content-type paths, ContentType objects
                or path strings (OR-matched, exact-or-subtree, e.g. "legal" also
                matches "legal:contract"; wildcards `legal:contract*`, `*nda*`).
            attribute: Restrict by attribute value, e.g.
                `["fiscal_year:2024|2025", "status:active"]`. Entries are ANDed,
                `|` ORs within one entry. Also `name` (has any value),
                `name:>value`, `name:prefix*`, `name:*text*`.
            max_results: Chunks to retrieve for context (1–50; server default 10).
            relevance_scoring: RelevanceScoring, .scoring_and_filtering (default),
                .scoring_only, or .none.
            model: LLM for answer generation; platform default if omitted.
            schema: Constrain the answer to structured output, a pydantic model
                class or a JSON-Schema dict (same inputs as `extract`, sent as
                the API's `response_format`; must describe an object). The answer
                then comes back as JSON *text* in `.answer`, parse it with
                `YourModel.model_validate_json(resp.answer)`.
            stream: Return an iterator of Server-Sent Events instead of the whole
                answer, for showing it as it generates. Composes with `schema`:
                the tokens then spell out the JSON, so concatenate them and parse
                at the end.

        Returns:
            `AskResponse` normally. When `stream=True`, an iterator of
            `SourcesEvent` (once, before generation), `TokenEvent` (repeatedly)
            and `DoneEvent` (last). Being a generator, nothing is sent until you
            start iterating, so request errors surface on the first step, not
            here. Iterate it fully or close it, so the connection is released.

        Raises:
            StreamError: If the server reports a failure mid-stream; the answer
                is incomplete at that point.
        """
        tag_ids = resolve_ids(cast("LightOn", self), tags) if tags else None
        body = _compact(
            query=query,
            workspace_id=_ids(workspaces),
            tag_id=tag_ids,
            file_id=_ids(files),
            content_type=_paths(content_type),
            attribute=attribute,
            max_results=max_results,
            relevance_scoring=relevance_scoring,
            model=model,
            response_format=as_json_schema(schema) if schema is not None else None,
        )
        if stream:
            return self._ask_stream({**body, "stream": True})
        return AskResponse.model_validate(
            self._request("POST", "/api/v3/ask", json=body)
        )

    def _ask_stream(self, body: dict[str, Any]) -> Generator[AskEvent, None, None]:
        """Yield typed events off the SSE stream, raising on an `error` event."""
        for name, data in _sse(self._stream("POST", "/api/v3/ask", json=body)):
            payload = json.loads(data) if data else {}
            if name == "error":
                raise StreamError(
                    f"ask stream failed: {payload.get('detail') or payload or 'no detail'}",
                    body=payload,
                )
            model = _EVENTS.get(name)
            if model is None:
                continue  # unknown event type: forward compatibility, not an error
            yield model.model_validate(payload)
