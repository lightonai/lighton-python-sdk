"""Client configuration schema."""

from __future__ import annotations

import httpx
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_BASE_URL = "https://api.lighton.ai"


def _default_timeout() -> httpx.Timeout:
    # Fast-fail on connect, but allow up to 2 min for the response body.
    return httpx.Timeout(120.0, connect=5.0)


class LightOnConfiguration(BaseModel):
    """Non-essential client knobs. api_key stays a direct LightOn() argument."""

    # transport/timeout are arbitrary httpx types, typed, not validated.
    model_config = ConfigDict(arbitrary_types_allowed=True)

    base_url: str = DEFAULT_BASE_URL
    timeout: httpx.Timeout = Field(default_factory=_default_timeout)
    retries: int = Field(
        default=3, ge=0, description="Connection-level retries (httpx transport)."
    )
    transport: httpx.BaseTransport | None = None  # lets tests inject MockTransport
    max_requests_per_minute: int | None = Field(
        default=1000,
        gt=0,
        description="Pace ALL requests to stay under this per-minute cap (min-interval "
        "gate in _request). Defaults to 1000, the API's limit for most endpoints; "
        "override if your account differs. Set None to disable pacing entirely.",
    )
    rate_limit_retries: int = Field(
        default=3,
        ge=0,
        description="On HTTP 429, retry this many times, waiting the Retry-After "
        "header when present (else exponential backoff). 0 disables.",
    )
