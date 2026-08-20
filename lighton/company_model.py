"""Company custom-model registration (active-record, see `_ActiveRecord`).

A CompanyModel is an LLM endpoint your company registers on its own account: your
routing string, optionally your address and your key, served through LightOn. Once
registered it is selectable wherever a model is (for example `ask(model=...)`).

Reads (list/get/refresh) are open to any member of the company; writes (create/save/
delete) need the CompanyAdmin role and raise `PermissionDeniedError` without it.

Three server behaviors shape this module:
  - `list` returns a bare JSON array, not a paginated envelope. `_ActiveRecord.list`
    recognizes both shapes, so nothing is overridden here.
  - `litellm_model`, `endpoint` and `api_key` are fixed at creation. PATCH ignores
    them silently rather than rejecting them, so `save()` never sends them.
  - `api_key` is write-only and never comes back in a response.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from pydantic import Field, SecretStr

from lighton._active_record import _ActiveRecord
from lighton.enums import ModelType
from lighton.utils import _compact

if TYPE_CHECKING:
    from lighton._client import LightOn

_BASE = "/api/v3/company/models"


class CompanyModel(_ActiveRecord):
    _base: ClassVar[str] = _BASE
    _resource: ClassVar[str] = "company model"

    id: str | None = Field(
        None, description="Server-assigned UUID; None until created/retrieved."
    )
    name: str = Field(description="Display name, unique within the company.")
    litellm_model: str = Field(
        description=(
            "Routing string, e.g. 'openai/gpt-4-turbo' or 'anthropic/claude-sonnet-4'. "
            "For an OpenAI-compatible endpoint (LM Studio, Ollama), prefix with "
            "'openai/'. Fixed at creation."
        )
    )
    model_type: str = Field(
        ModelType.large_language_model,
        description=(
            "Model type, e.g. 'Large Language Model' or 'Embedding Model'. See the "
            "ModelType vocabulary; the server does not restrict it to those values."
        ),
    )
    endpoint: str | None = Field(
        None,
        description=(
            "Base URL of your own deployment; None to use the provider's. Fixed at creation."
        ),
    )
    api_key: SecretStr | None = Field(
        None,
        description=(
            "Credential for the endpoint, sent on create() and never returned by the "
            "API. Fixed at creation. Use .get_secret_value() to read it back locally."
        ),
    )
    temperature: float | None = Field(
        None,
        description=(
            "Sampling temperature (0 to 2) sent on every request to this model. None "
            "lets each calling feature use its own value."
        ),
    )
    # Read-only, populated from responses.
    technical_name: str | None = Field(
        None, description="Identifier the gateway routes on (read-only)."
    )
    enabled: bool | None = Field(
        None, description="Whether the model is active (read-only)."
    )
    is_default: bool | None = Field(
        None, description="Whether this is the company's default custom model."
    )
    required_temperature: float | None = Field(
        None,
        description=(
            "The only temperature this model accepts, when it accepts exactly one; "
            "None for every other model (read-only)."
        ),
    )
    max_temperature: float | None = Field(
        None,
        description=(
            "Highest temperature this model's provider accepts, None when it "
            "publishes no bound (read-only)."
        ),
    )

    # --- instance lifecycle ------------------------------------------------
    def create(self, client: LightOn) -> CompanyModel:
        """Register this model and bind the client for later lifecycle calls.

        Args:
            client: The client to register the model with and bind to `self`.

        Returns:
            `self`, updated with the id and the server-derived read-only fields.

        Raises:
            PermissionDeniedError: If the key is not a company admin's.
            LightOnAPIError: 400 if the temperature is above the provider's ceiling,
                or if the deployment cannot serve company custom models at all.
        """
        payload = _compact(
            name=self.name,
            litellm_model=self.litellm_model,
            model_type=self.model_type,
            endpoint=self.endpoint,
            api_key=self.api_key.get_secret_value() if self.api_key else None,
            temperature=self.temperature,
        )
        data = client._request("POST", _BASE, json=payload)
        self._client = client
        return self._absorb(data)

    def save(self) -> CompanyModel:
        """Persist local edits to name/is_default/temperature (PATCH).

        Only those three are sent. `litellm_model`, `endpoint` and `api_key` are fixed
        at creation: the credential is write-only in the gateway, so it cannot be
        rewritten without first being read back, and it cannot be read back. Changing
        any of them means registering a new model. The API ignores them silently rather
        than rejecting them, so sending them would look like it worked.

        Returns:
            `self`, refreshed with the server's response.

        Raises:
            PermissionDeniedError: If the key is not a company admin's.
            LightOnAPIError: 400 if the temperature is above the provider's ceiling.
        """
        data = self._api(
            "PATCH",
            f"{_BASE}/{self.id}",
            json=_compact(
                name=self.name,
                is_default=self.is_default,
                temperature=self.temperature,
            ),
        )
        return self._absorb(data)
