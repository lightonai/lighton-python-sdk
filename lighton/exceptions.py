"""LightOn SDK exceptions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx


class LightOnError(Exception):
    """Base class for every error raised by this SDK."""


class LightOnConnectionError(LightOnError):
    """Transport failure before any response was received (DNS, timeout, reset)."""


class MalformedResponseError(LightOnError):
    """A 2xx response body was not valid JSON."""


class StreamError(LightOnError):
    """The server sent an `error` event partway through a stream.

    Not a `LightOnAPIError`: the HTTP response was a perfectly good 200 and the
    failure happened during generation, so there is no status code to carry. The
    answer is incomplete, which is why this raises instead of arriving as one more
    event a caller could mistake for a finished answer. `body` holds the payload.
    """

    def __init__(self, message: str, *, body: Any = None) -> None:
        super().__init__(message)
        self.body = body


class LightOnAPIError(LightOnError):
    """The API returned a non-2xx response.

    `status_code` is the HTTP status, and `body` is the decoded error payload
    exactly as the API sent it (the parsed JSON, or the raw text when it wasn't
    JSON, or None when there was no body). Nothing is stripped from it, so
    anything this class doesn't name is still readable there.

    `fields` holds the per-field validation errors of a 422, keyed by field name:
    `{"choices": [{"error": "invalid", "detail": "must be a non-empty list"}]}`.
    The top-level `detail` of a validation error is a constant sentence, so this
    is the part that says what actually went wrong; it is already folded into the
    message, and this attribute is for callers that want to branch on it. Empty
    for every error that isn't a field-level rejection.

    `index` is set only on a **batch** endpoint failure: the 0-based position of
    the action that failed. Batch endpoints validate every action's fields up
    front (a field-level 422 executes nothing), then run in order and stop at the
    first domain error, so the actions before `index` are already applied and the
    one at `index` is not. Every action is idempotent, so the fix is to correct
    that one and resend the whole list. None for a single-action request, which
    never carries an index.
    """

    def __init__(self, message: str, *, status_code: int, body: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body
        self.fields: dict[str, list[dict[str, Any]]] = _fields(body)
        self.index: int | None = _index(body)


class AuthenticationError(LightOnAPIError):
    """401, bad or missing API key (the request is not authenticated)."""


class PermissionDeniedError(LightOnAPIError):
    """403, authenticated, but the key lacks permission for this operation.

    Distinct from `AuthenticationError`: the credentials are valid, but the caller
    isn't allowed (e.g. an endpoint that requires the CompanyAdmin role).
    """


class NotFoundError(LightOnAPIError):
    """404, the resource does not exist."""


class RateLimitError(LightOnAPIError):
    """429, too many requests.

    `retry_after` is the seconds to wait before retrying, from the `Retry-After`
    response header when the server sends it (else None).
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        body: Any = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code, body=body)
        self.retry_after = retry_after


class ServerError(LightOnAPIError):
    """5xx, the API failed to handle the request."""


class MaintenanceError(ServerError):
    """503 during a planned maintenance window, not a crash.

    A `ServerError` subclass, so existing `except ServerError` handlers keep
    working; catch this specifically to tell "come back later" apart from "this
    broke", since only one of the two is worth retrying.

    `mode` is `full_shutdown` or `warning_banner` (both block the request),
    `reason` is operator-supplied text, `started_at` is when the window opened,
    and `endpoint_categories` names the affected categories, empty meaning every
    endpoint. The untouched payload is always on `.body`.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        body: Any = None,
        mode: str | None = None,
        reason: str | None = None,
        started_at: datetime | None = None,
        endpoint_categories: list[str] | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code, body=body)
        self.mode = mode
        self.reason = reason
        self.started_at = started_at
        self.endpoint_categories = endpoint_categories or []


_MAINTENANCE = "service_maintenance"

_STATUS_MAP = {
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    429: RateLimitError,
}


def from_response(response: httpx.Response) -> LightOnAPIError:
    """Map an httpx response to the right exception subclass."""
    body = _safe_body(response)
    cls = _STATUS_MAP.get(response.status_code)
    if cls is None:
        cls = ServerError if response.status_code >= 500 else LightOnAPIError
    detail = body.get("detail") if isinstance(body, dict) else body
    message = f"{response.status_code} {response.reason_phrase}"
    if detail:
        message = f"{message}: {detail}"
    summary = _field_summary(_fields(body))
    if summary:
        message = f"{message} ({summary})"
    index = _index(body)
    if index is not None:
        message = f"{message} (action {index})"
    if cls is RateLimitError:
        return RateLimitError(
            message,
            status_code=response.status_code,
            body=body,
            retry_after=_retry_after(response),
        )
    if isinstance(body, dict) and body.get("error") == _MAINTENANCE:
        return MaintenanceError(
            message,
            status_code=response.status_code,
            body=body,
            mode=body.get("mode"),
            reason=body.get("reason"),
            started_at=_timestamp(body.get("started_at")),
            endpoint_categories=body.get("endpoint_category_names"),
        )
    return cls(message, status_code=response.status_code, body=body)


def _retry_after(response: httpx.Response) -> float | None:
    """Seconds from the `Retry-After` header. ponytail: seconds form only, the
    rarely-used HTTP-date form returns None; add date parsing if the API uses it."""
    raw = response.headers.get("Retry-After")
    try:
        return float(raw) if raw is not None else None
    except ValueError:
        return None


def _index(body: Any) -> int | None:
    """0-based position of the failing action inside a batch, or None.

    `isinstance(value, int)` rather than truthiness: index 0 is a real answer.
    """
    value = body.get("index") if isinstance(body, dict) else None
    return value if isinstance(value, int) else None


def _fields(body: Any) -> dict[str, list[dict[str, Any]]]:
    """Per-field validation errors keyed by field name, or {} when there are none.

    Passed through in the API's own shape, so the machine-readable `error` code
    beside each `detail` survives. Defensive at every level because this runs
    while an exception is being built: a server shape change has to degrade to an
    empty mapping, never raise on top of the error it was meant to describe. The
    untouched payload stays on `.body` either way. A key whose list yields no
    entries is dropped, so a non-empty result always has something to say.
    """
    raw = body.get("fields") if isinstance(body, dict) else None
    if not isinstance(raw, dict):
        return {}
    fields: dict[str, list[dict[str, Any]]] = {}
    for name, errors in raw.items():
        if not isinstance(errors, list):
            continue
        entries = [e for e in errors if isinstance(e, dict)]
        if entries:
            fields[str(name)] = entries
    return fields


def _field_summary(fields: dict[str, list[dict[str, Any]]]) -> str:
    """Render `fields` for the message: `name: why, why; name: why`.

    Falls back to the `error` code when an entry carries no readable `detail`, so
    a named field is never left without a cause. ponytail: uncapped, `fields` is
    keyed by request-body field and so bounded by the request schema; cap it here
    if an endpoint ever reports per-item errors.
    """
    parts = []
    for name, errors in fields.items():
        causes = [c for c in (_cause(e) for e in errors) if c]
        if causes:
            parts.append(f"{name}: {', '.join(causes)}")
    return "; ".join(parts)


def _cause(entry: dict[str, Any]) -> str | None:
    for key in ("detail", "error"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _timestamp(raw: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp, or None. The raw value stays on `.body`."""
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _safe_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text or None
