"""Synchronous LightOn API client.

The 4 primary verbs (ask, search, parse, extract) are mixed in from lighton/verbs/;
this module holds only the transport core (auth, _request, lifecycle). CRUD-style
groups (files, ingestion, keys) hang off the active-record resources instead.
"""

from __future__ import annotations

import os
import random
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx

from lighton import exceptions as exc
from lighton.types import LightOnConfiguration
from lighton.verbs import AskMixin, ExtractMixin, ParseMixin, SearchMixin


class _RateGate:
    """Thread-safe minimum-interval pacer to hold a per-minute request ceiling.

    ponytail: even spacing, not a burst-allowing token bucket, simplest thing that
    keeps concurrent threads under a per-minute cap. Swap for a token bucket if you
    need to allow short bursts. Clock/sleep are injectable so tests need no wall time.
    """

    def __init__(
        self,
        per_minute: int,
        *,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._interval = 60.0 / per_minute
        self._sleep = sleep
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._next = 0.0

    def acquire(self) -> None:
        """Block just long enough that requests stay spaced by the interval."""
        with self._lock:
            now = self._monotonic()
            wait = self._next - now
            self._next = max(now, self._next) + self._interval
        if wait > 0:
            self._sleep(wait)


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
        # httpx.HTTPTransport(retries=) retries connection errors only (exp. backoff).
        # HTTP 429 cooldown/retry is handled separately in _request; 5xx isn't retried.
        transport = config.transport or httpx.HTTPTransport(retries=config.retries)
        self._http = httpx.Client(
            base_url=config.base_url.rstrip("/"),
            timeout=config.timeout,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
        )
        self._gate = (
            _RateGate(config.max_requests_per_minute)
            if config.max_requests_per_minute
            else None
        )
        self._rate_limit_retries = config.rate_limit_retries

    # --- lifecycle ---------------------------------------------------------
    def __enter__(self) -> "LightOn":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    # --- transport ---------------------------------------------------------
    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Send a request, raise on error, return parsed JSON (or None for empty 2xx).

        Paces requests under the configured per-minute cap and, on HTTP 429, waits
        the Retry-After cooldown (or exponential backoff) and retries up to
        `rate_limit_retries` times. All callers route through here, so both the cap
        and the cooldown apply to every endpoint uniformly.
        """
        for attempt in range(self._rate_limit_retries + 1):
            if self._gate is not None:
                self._gate.acquire()
            try:
                response = self._http.request(method, path, **kwargs)
            except httpx.TransportError as e:
                raise exc.LightOnConnectionError(str(e)) from e
            if response.is_success:
                if not response.content:
                    return None
                try:
                    return response.json()
                except ValueError as e:
                    raise exc.MalformedResponseError(
                        f"expected JSON but got: {response.text[:200]!r}"
                    ) from e
            error = exc.from_response(response)
            if (
                isinstance(error, exc.RateLimitError)
                and attempt < self._rate_limit_retries
            ):
                time.sleep(_cooldown(error.retry_after, attempt))
                continue
            raise error
        raise AssertionError("unreachable")  # loop either returns or raises


def _cooldown(retry_after: float | None, attempt: int) -> float:
    """Seconds to wait before a 429 retry: honor Retry-After, else backoff+jitter.

    ponytail: exponential backoff capped at 60s with small jitter; good enough for a
    rate-limit cooldown. Uses `random` for jitter, fine at SDK runtime.
    """
    if retry_after is not None:
        return retry_after
    return min(60.0, 2.0**attempt) + random.uniform(0.0, 0.5)
