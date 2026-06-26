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

    # transport/timeout are arbitrary httpx types — typed, not validated.
    model_config = ConfigDict(arbitrary_types_allowed=True)

    base_url: str = DEFAULT_BASE_URL
    timeout: httpx.Timeout = Field(default_factory=_default_timeout)
    retries: int = Field(default=3, ge=0)
    transport: httpx.BaseTransport | None = None  # lets tests inject MockTransport
