"""LightOn SDK exceptions."""

from __future__ import annotations

from typing import Any

import httpx


class LightOnError(Exception):
    """Base class for every error raised by this SDK."""


class LightOnConnectionError(LightOnError):
    """Transport failure before any response was received (DNS, timeout, reset)."""


class MalformedResponseError(LightOnError):
    """A 2xx response body was not valid JSON."""


class LightOnAPIError(LightOnError):
    """The API returned a non-2xx response."""

    def __init__(self, message: str, *, status_code: int, body: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


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
    if cls is RateLimitError:
        return RateLimitError(
            message,
            status_code=response.status_code,
            body=body,
            retry_after=_retry_after(response),
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


def _safe_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text or None
