"""Streaming `ask` events (pure data, per the `types/` rule).

One model per Server-Sent Event the endpoint emits. `type` is a literal
discriminator, so callers can switch on `event.type` or use `isinstance`,
whichever reads better at the call site.

The `error` event has no model on purpose: it means the answer is incomplete, so
the SDK raises `StreamError` rather than handing back an event a caller could
quietly ignore and mistake for a finished answer.
"""

from __future__ import annotations

from builtins import list as _list
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from lighton.types.api import AskResultItem


class SourcesEvent(BaseModel):
    """The retrieved chunks, sent once before generation starts."""

    model_config = ConfigDict(extra="ignore")

    type: Literal["sources"] = Field("sources", description="Event discriminator.")
    results: _list[AskResultItem] = Field(
        default_factory=list,
        description="Retrieved chunks used as context, the same items `ask` returns.",
    )


class TokenEvent(BaseModel):
    """One chunk of the answer as it generates."""

    model_config = ConfigDict(extra="ignore")

    type: Literal["token"] = Field("token", description="Event discriminator.")
    text: str = Field("", description="Answer text to append; may be several tokens.")


class DoneEvent(BaseModel):
    """Generation finished; no further events follow."""

    model_config = ConfigDict(extra="ignore")

    type: Literal["done"] = Field("done", description="Event discriminator.")


AskEvent = SourcesEvent | TokenEvent | DoneEvent
