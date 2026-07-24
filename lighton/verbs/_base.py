"""Shared base for the verb mixins.

Declares the only client surface the verbs call, `_request`. `LightOn`
overrides it with the real transport; the stub exists so the mixins type-check
in isolation.
"""

from __future__ import annotations

from typing import Any


class _VerbClient:
    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        raise NotImplementedError  # provided by LightOn
