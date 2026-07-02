"""Shared active-record plumbing for the resource models.

Read-side lifecycle (list/get/refresh/delete) and the client-binding internals
(`_bind`/`_api`/`_absorb`) are identical across Workspace/ApiKey/File, so they live
here. What genuinely diverges stays on the subclass: the field schema, `create()`
(JSON vs multipart body), and `save()` (per-resource PATCH payload).

Subclasses set two ClassVars: `_base` (URL path) and `_resource` (name used in error
messages). `_absorb` overwrites only fields present in the response, so one-time or
local-only fields (ApiKey.key, File.path) survive a later refresh().
"""

from __future__ import annotations

# The list() classmethod shadows builtin list in annotations (class scope).
from builtins import list as _list
from typing import TYPE_CHECKING, ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

if TYPE_CHECKING:
    from lighton._client import LightOn


class _ActiveRecord(BaseModel):
    # Responses carry extra fields the curated schema doesn't model; ignore them.
    model_config = ConfigDict(extra="ignore")

    _base: ClassVar[str]  # e.g. "/api/v3/workspaces"
    _resource: ClassVar[str]  # e.g. "workspace" — used in error messages

    id: int | str | None = Field(
        None, description="Server-assigned id; None until created/retrieved."
    )

    _client: LightOn | None = PrivateAttr(default=None)

    # --- class-level (no instance yet) -------------------------------------
    @classmethod
    def list(cls, client: LightOn, **params: object) -> _list[Self]:
        """List every resource, following pagination to the end.

        Args:
            client: The client used to make the request and bind to each result.
            **params: Optional query filters (e.g. workspace_id) sent on the first page.

        Returns:
            All matching resources, each bound to `client`.
        """
        query: dict[str, object] | None = params or None
        items: _list[Self] = []
        path: str | None = cls._base
        while path:  # follow pagination — no silent truncation
            page = client._request("GET", path, params=query)
            items.extend(cls._bind(client, row) for row in page["results"])
            path = page.get("next")
            query = None  # `next` already carries the query string
        return items

    @classmethod
    def get(cls, client: LightOn, id: int | str) -> Self:
        """Fetch a single resource by id.

        Args:
            client: The client used to make the request and bind to the result.
            id: The resource id to retrieve.

        Returns:
            The resource, bound to `client`.
        """
        return cls._bind(client, client._request("GET", f"{cls._base}/{id}"))

    # --- instance lifecycle ------------------------------------------------
    def refresh(self) -> Self:
        """Re-fetch this resource from the API (GET).

        Returns:
            `self`, updated with the latest field values.
        """
        return self._absorb(self._api("GET", f"{self._base}/{self.id}"))

    def delete(self) -> None:
        """Delete this resource and clear its local id."""
        self._api("DELETE", f"{self._base}/{self.id}")
        self.id = None

    # --- internals ---------------------------------------------------------
    def _bound_client(self) -> LightOn:
        """Return the bound client, or raise if this instance isn't persisted yet.

        Returns:
            The client bound by create()/get()/list().

        Raises:
            ValueError: If the instance has no id or no bound client.
        """
        if self.id is None or self._client is None:
            raise ValueError(f"{self._resource} must be created or retrieved first")
        return self._client

    def _api(self, method: str, path: str, **kwargs: object):
        return self._bound_client()._request(method, path, **kwargs)

    @classmethod
    def _bind(cls, client: LightOn, data: dict) -> Self:
        obj = cls.model_validate(data)
        obj._client = client
        return obj

    def _absorb(self, data: dict | None) -> Self:
        """Copy returned fields onto self, keeping _client and any local-only fields."""
        if data:
            fresh = self.model_validate(data)
            for field in type(self).model_fields:
                if field in data:  # only overwrite what the response returned
                    setattr(self, field, getattr(fresh, field))
        return self
