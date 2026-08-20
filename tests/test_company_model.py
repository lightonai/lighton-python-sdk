"""Active-record CompanyModel: bare-array list, create-only secret, narrow PATCH."""

import json

import httpx
import pytest
from pydantic import SecretStr

from lighton import CompanyModel, LightOn, ModelType
from lighton.company_model import _BASE
from lighton.exceptions import NotFoundError, PermissionDeniedError
from lighton.types import LightOnConfiguration

_UUID = "a08cff52-1a96-49f4-9f28-84a060b9264c"


def _model(**overrides) -> dict:
    """A server response body, with the read-only fields the API derives."""
    return {
        "id": _UUID,
        "name": "Gemma 4",
        "technical_name": f"custom-42-{_UUID}",
        "litellm_model": "openai/google/gemma-4-e4b",
        "model_type": "Large Language Model",
        "endpoint": "http://localhost:1234/v1",
        "enabled": True,
        "is_default": False,
        "temperature": 0.2,
        "required_temperature": None,
        "max_temperature": None,
        **overrides,
    }


def _client(handler) -> LightOn:
    return LightOn(
        "k",
        config=LightOnConfiguration(
            transport=httpx.MockTransport(handler), max_requests_per_minute=None
        ),
    )


@pytest.fixture
def sent() -> list[dict]:
    """Request bodies captured by the `client` fixture, in order."""
    return []


@pytest.fixture
def client(sent):
    def handler(request: httpx.Request) -> httpx.Response:
        m, path = request.method, request.url.path
        if request.content:
            sent.append(json.loads(request.content))
        if m == "GET" and path == _BASE:
            # A bare array, not a {"results": ..., "next": ...} envelope.
            return httpx.Response(200, json=[_model(), _model(name="Mistral")])
        if m == "POST" and path == _BASE:
            return httpx.Response(201, json=_model())
        if m == "PATCH":
            return httpx.Response(200, json=_model(is_default=True))
        if m == "DELETE":
            return httpx.Response(204)
        if m == "GET":
            return httpx.Response(200, json=_model())
        return httpx.Response(200, json={})

    return _client(handler)


def test_list_parses_a_bare_array(client):
    # No `next`-following test here on purpose: unlike /keys, this endpoint is not
    # paginated. The live schema types the 200 as `type: array`, and the view returns
    # a plain Response(list). The paginated branch of _ActiveRecord.list is covered by
    # test_apikey.py::test_list_follows_pagination.
    models = CompanyModel.list(client)
    assert [m.name for m in models] == ["Gemma 4", "Mistral"]
    assert models[0].id == _UUID
    assert models[0].technical_name == f"custom-42-{_UUID}"


def test_create_binds_and_populates_read_only_fields(client):
    m = CompanyModel(name="Gemma 4", litellm_model="openai/google/gemma-4-e4b").create(
        client
    )
    assert m.id == _UUID and m.enabled is True
    assert m.technical_name == f"custom-42-{_UUID}"


def test_create_defaults_model_type_to_llm(client, sent):
    CompanyModel(name="Gemma 4", litellm_model="openai/google/gemma-4-e4b").create(
        client
    )
    assert sent[0]["model_type"] == ModelType.large_language_model


def test_create_sends_the_plaintext_key_and_omits_unset_fields(client, sent):
    CompanyModel(
        name="Gemma 4",
        litellm_model="openai/google/gemma-4-e4b",
        api_key=SecretStr("sk-secret"),
    ).create(client)
    assert sent[0]["api_key"] == "sk-secret"
    assert "endpoint" not in sent[0] and "temperature" not in sent[0]


def test_api_key_survives_a_refresh_that_omits_it(client):
    m = CompanyModel(
        name="Gemma 4",
        litellm_model="openai/google/gemma-4-e4b",
        api_key=SecretStr("sk-secret"),
    ).create(client)
    m.refresh()
    assert m.api_key is not None and m.api_key.get_secret_value() == "sk-secret"


def test_api_key_does_not_leak_in_repr(client):
    m = CompanyModel(
        name="Gemma 4",
        litellm_model="openai/google/gemma-4-e4b",
        api_key=SecretStr("sk-secret"),
    )
    assert "sk-secret" not in repr(m)


def test_save_sends_only_the_mutable_fields(client, sent):
    m = CompanyModel.get(client, _UUID)
    m.is_default = True
    m.save()
    assert sent[-1] == {"name": "Gemma 4", "is_default": True, "temperature": 0.2}


def test_save_absorbs_the_response(client):
    m = CompanyModel.get(client, _UUID)
    m.is_default = True
    assert m.save().is_default is True


def test_delete_clears_id(client):
    m = CompanyModel.get(client, _UUID)
    m.delete()
    assert m.id is None


def test_unsaved_instance_cannot_be_saved():
    with pytest.raises(ValueError):
        CompanyModel(name="Gemma 4", litellm_model="openai/gpt-4-turbo").save()


def test_unknown_uuid_raises_not_found():
    client = _client(lambda _r: httpx.Response(404, json={"detail": "not found"}))
    with pytest.raises(NotFoundError):
        CompanyModel.get(client, _UUID)


def test_non_admin_create_raises_permission_denied():
    client = _client(
        lambda _r: httpx.Response(403, json={"detail": "Admin access required."})
    )
    with pytest.raises(PermissionDeniedError):
        CompanyModel(name="Gemma 4", litellm_model="openai/gpt-4-turbo").create(client)
