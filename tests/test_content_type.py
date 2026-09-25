"""ContentType.list: parses the taxonomy tree (nested children + attributes)."""

import json

import httpx
import pytest

from lighton import (
    MAX_CONTENT_TYPE_ACTIONS,
    AttributeType,
    ContentType,
    ContentTypeAction,
    ContentTypeActionType,
    LightOn,
    LightOnConfiguration,
)
from lighton.exceptions import NotFoundError


def make_client(handler) -> LightOn:
    return LightOn(
        "k",
        config=LightOnConfiguration(
            transport=httpx.MockTransport(handler), max_requests_per_minute=None
        ),
    )


def test_list_parses_tree_and_sends_params():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        seen["query"] = dict(req.url.params)
        return httpx.Response(
            200,
            json={
                "content_types": [
                    {
                        "path": "legal",
                        "code": "legal",
                        "label": "Legal",
                        "source": "company",
                        "attributes": [
                            {
                                "name": "jurisdiction",
                                "type": "select",
                                "choices": ["FR", "US"],
                            }
                        ],
                        "children": [
                            {
                                "path": "legal:contract",
                                "code": "contract",
                                "label": "Contract",
                            }
                        ],
                    }
                ],
                "can_edit": True,
            },
        )

    types = ContentType.list(
        make_client(handler), path="legal", include_attributes=True
    )
    assert seen["path"] == "/api/v3/content-types"
    assert seen["query"]["path"] == "legal"
    assert len(types) == 1
    legal = types[0]
    assert legal.path == "legal"
    assert legal.attributes[0].name == "jurisdiction"
    assert legal.attributes[0].choices == ["FR", "US"]
    # nested child parsed recursively
    assert legal.children[0].path == "legal:contract"


def _writer(response):
    """A client whose POSTs record the body and reply with `response`."""
    sent = {}

    def handler(req: httpx.Request) -> httpx.Response:
        sent["path"] = req.url.path
        sent["body"] = json.loads(req.content)
        return httpx.Response(200, json=response)

    return make_client(handler), sent


def test_define_sends_the_action_and_parses_the_node():
    node = {"path": "legal:nda", "code": "nda", "label": "NDA", "description": ""}
    client, sent = _writer(node)

    ct = ContentType.define(client, "nda", "NDA", parent="legal")

    assert sent["path"] == "/api/v3/content-types"
    assert sent["body"] == {
        "action": "define_content_type",
        "code": "nda",
        "label": "NDA",
        "parent_path": "legal",
    }
    assert ct.path == "legal:nda"


def test_define_accepts_a_content_type_as_the_parent():
    parent = ContentType(path="legal", code="legal", label="Legal")
    client, sent = _writer({"path": "legal:nda", "code": "nda", "label": "NDA"})

    ContentType.define(client, "nda", "NDA", parent=parent)
    assert sent["body"]["parent_path"] == "legal"  # coerced via .path


def test_undefine_sends_the_path():
    client, sent = _writer(None)
    ContentType.undefine(client, ContentType(path="legal", code="legal", label="Legal"))
    assert sent["body"] == {
        "action": "undefine_content_type",
        "content_type_path": "legal",
    }


def test_define_attribute_sends_choices_and_parses_the_definition():
    client, sent = _writer(
        {"name": "region", "label": "Region", "type": "select", "choices": ["FR", "US"]}
    )

    attr = ContentType.define_attribute(
        client, "legal", "region", AttributeType.select, choices=["FR", "US"]
    )

    assert sent["body"] == {
        "action": "define_attribute",
        "content_type_path": "legal",
        "name": "region",
        "attribute_type": "select",
        "choices": ["FR", "US"],
    }
    assert attr.name == "region" and attr.choices == ["FR", "US"]


def test_define_attribute_rejects_a_select_without_choices():
    # The API 422s on this; refusing locally saves the round trip.
    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("no request should be made")

    # the enum members and, a StrEnum making them equal, the canonical strings too.
    # The API's aliases (multi_select, multiselect) are deliberately not matched.
    for kind in (
        AttributeType.select,
        AttributeType.multi_select,
        "select",
        "multi-select",
    ):
        with pytest.raises(ValueError, match="choices"):
            ContentType.define_attribute(make_client(handler), "legal", "x", kind)


def test_undefine_attribute_sends_the_path_and_name():
    client, sent = _writer(None)
    ContentType.undefine_attribute(client, "legal", "region")
    assert sent["body"] == {
        "action": "undefine_attribute",
        "content_type_path": "legal",
        "name": "region",
    }


def test_adopt_imports_template_roots():
    client, sent = _writer(
        {"content_types": [{"path": "legal", "code": "legal", "label": "Legal"}]}
    )

    adopted = ContentType.adopt(client, ["legal", "finance"])

    assert sent["body"] == {"action": "adopt", "content_types": ["legal", "finance"]}
    assert [n.path for n in adopted] == ["legal"]


def test_templates_parses_the_per_path_attribute_map():
    # A template hangs the whole subtree's attributes off the root as a map,
    # unlike a ContentType, whose `attributes` is its own flat list.
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api/v3/content-types/templates"
        return httpx.Response(
            200,
            json={
                "content_types": [
                    {
                        "path": "legal",
                        "code": "legal",
                        "label": "Legal",
                        "children": [
                            {"path": "legal:nda", "code": "nda", "label": "NDA"}
                        ],
                        "attributes": {
                            "legal": [
                                {
                                    "name": "jurisdiction",
                                    "type": "multi-select",
                                    "choices": ["FR"],
                                }
                            ]
                        },
                    }
                ]
            },
        )

    [tpl] = ContentType.templates(make_client(handler))
    assert tpl.path == "legal"
    assert [c.path for c in tpl.children] == ["legal:nda"]
    assert tpl.attributes["legal"][0].name == "jurisdiction"


def test_batch_posts_every_action_in_one_request():
    requests = []

    def handler(req: httpx.Request) -> httpx.Response:
        requests.append(req)
        return httpx.Response(
            200,
            json={
                "results": [
                    {"status": 201, "data": {"path": "legal"}},
                    {"status": 201, "data": {"name": "flag"}},
                ]
            },
        )

    ContentType.batch(
        make_client(handler),
        [
            ContentTypeAction.adopt(["legal"]),
            ContentTypeAction.define_attribute("legal", "flag", AttributeType.boolean),
        ],
    )

    assert len(requests) == 1, "a batch must be exactly one round trip"
    assert requests[0].url.path == "/api/v3/content-types/batch"
    assert json.loads(requests[0].content) == {
        "actions": [
            {"action": "adopt", "content_types": ["legal"]},
            {
                "action": "define_attribute",
                "content_type_path": "legal",
                "name": "flag",
                "attribute_type": "boolean",
            },
        ]
    }


def test_batch_sends_the_same_bodies_as_the_single_action_methods():
    """ContentTypeAction._body() is the one wire encoder, so the paths can't drift."""
    single, batched = [], []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        if req.url.path.endswith("/batch"):
            batched.extend(body["actions"])
            return httpx.Response(
                200, json={"results": [{"status": 200, "data": None}] * 5}
            )
        single.append(body)
        # one body the node, attribute and adopt parsers can all read
        return httpx.Response(
            200,
            json={
                "content_types": [],
                "path": "x",
                "code": "x",
                "label": "X",
                "name": "region",
            },
        )

    client = make_client(handler)
    ContentType.adopt(client, ["legal"])
    ContentType.define(client, "nda", "NDA", parent="legal", inherit_attributes=False)
    ContentType.define_attribute(
        client, "legal", "region", AttributeType.select, choices=["FR"], required=False
    )
    ContentType.undefine_attribute(client, "legal", "region")
    ContentType.undefine(client, "legal")
    ContentType.batch(
        client,
        [
            ContentTypeAction.adopt(["legal"]),
            ContentTypeAction.define(
                "nda", "NDA", parent="legal", inherit_attributes=False
            ),
            ContentTypeAction.define_attribute(
                "legal",
                "region",
                AttributeType.select,
                choices=["FR"],
                required=False,
            ),
            ContentTypeAction.undefine_attribute("legal", "region"),
            ContentTypeAction.undefine("legal"),
        ],
    )

    assert single == batched


def test_batch_parses_results_in_order():
    client, _ = _writer(
        {
            "results": [
                {"status": 201, "data": {"path": "compliance"}},
                {"status": 204, "data": None},
                {"status": 200, "data": {"name": "owner", "type": "text"}},
            ]
        }
    )

    results = ContentType.batch(
        client,
        [
            ContentTypeAction.define("compliance", "Compliance"),
            ContentTypeAction.undefine_attribute("compliance", "stale"),
            ContentTypeAction.define_attribute(
                "compliance", "owner", AttributeType.text
            ),
        ],
    )

    assert [r.status for r in results] == [201, 204, 200]
    assert results[1].data is None, "the 204 verbs carry no data"
    assert results[2].data == {"name": "owner", "type": "text"}


def test_batch_refuses_more_than_fifty_actions():
    action = ContentTypeAction.undefine("legal")

    def _no_request(req: httpx.Request) -> httpx.Response:
        raise AssertionError(f"no request should be made, got {req.url}")

    with pytest.raises(ValueError, match="50"):
        ContentType.batch(
            make_client(_no_request), [action] * (MAX_CONTENT_TYPE_ACTIONS + 1)
        )

    # and the boundary itself is accepted: an off-by-one here is the plausible bug
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [{"status": 204, "data": None}] * MAX_CONTENT_TYPE_ACTIONS
            },
        )

    assert (
        len(
            ContentType.batch(make_client(handler), [action] * MAX_CONTENT_TYPE_ACTIONS)
        )
        == MAX_CONTENT_TYPE_ACTIONS
    )


def test_batch_is_a_local_no_op_when_empty():
    def _no_request(req: httpx.Request) -> httpx.Response:
        raise AssertionError(f"no request should be made, got {req.url}")

    assert ContentType.batch(make_client(_no_request), []) == []


def test_batch_passes_raw_dicts_through():
    client, sent = _writer({"results": [{"status": 200, "data": None}] * 2})

    raw = {"action": "some_future_verb", "content_type_path": "legal", "extra": 1}
    ContentType.batch(client, [ContentTypeAction.undefine("legal"), raw])

    assert sent["body"]["actions"][1] == raw, "a raw dict must reach the wire untouched"


def test_batch_reports_the_failing_action_index():
    """`index` rides on the status-mapped class, so `except NotFoundError` still works."""

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "unknown parent", "index": 1})

    actions = [
        ContentTypeAction.define("compliance", "Compliance"),
        ContentTypeAction.define("audit", "Audit", parent="nope:not-a-type"),
    ]
    with pytest.raises(NotFoundError) as excinfo:
        ContentType.batch(make_client(handler), actions)

    assert excinfo.value.index == 1
    assert "action 1" in str(excinfo.value), "the position belongs in the message too"
    # which is what makes the offender addressable, and the prefix already applied
    assert actions[excinfo.value.index].parent_path == "nope:not-a-type"


def test_content_type_action_rejects_a_verb_missing_its_fields():
    # pydantic's ValidationError subclasses ValueError; refused before any request
    with pytest.raises(ValueError, match="code, label"):
        ContentTypeAction(action=ContentTypeActionType.define_content_type)

    with pytest.raises(ValueError, match="content_type_path"):
        ContentTypeAction(action=ContentTypeActionType.undefine_content_type)

    with pytest.raises(ValueError, match="content_types"):
        ContentTypeAction(action=ContentTypeActionType.adopt, content_types=[])


def test_content_type_action_rejects_a_misspelled_field():
    # a write model: a typo must not silently vanish from the request body
    with pytest.raises(ValueError, match="atribute_type"):
        ContentTypeAction(
            action=ContentTypeActionType.define_attribute,
            content_type_path="legal",
            name="region",
            attribute_type=AttributeType.text,
            atribute_type="typo",  # ty: ignore[unknown-argument]
        )


def test_define_omits_what_you_did_not_set():
    client, sent = _writer({"path": "x", "code": "x", "label": "X"})
    ContentType.define(client, "x", "X")
    assert sent["body"] == {"action": "define_content_type", "code": "x", "label": "X"}


def test_a_false_flag_is_sent_not_dropped():
    """The other half of "omits what you did not set": False is a value, not unset.

    `_body()` drops on None alone. Were it ever to drop on falsiness (or on
    `exclude_defaults`), `inherit_attributes=False` would vanish and the server
    would apply its default of True, silently inheriting attributes the caller
    asked it not to — and it would vanish from the batch path identically, so the
    single-equals-batch test would stay green. Hence a body assertion on each.
    """
    client, sent = _writer({"path": "x", "code": "x", "label": "X"})
    ContentType.define(client, "x", "X", inherit_attributes=False)
    assert sent["body"]["inherit_attributes"] is False

    client, sent = _writer({"name": "region", "type": "text"})
    ContentType.define_attribute(
        client, "legal", "region", AttributeType.text, required=False
    )
    assert sent["body"]["required"] is False

    client, sent = _writer({"results": [{"status": 201, "data": None}] * 2})
    ContentType.batch(
        client,
        [
            ContentTypeAction.define("x", "X", inherit_attributes=False),
            ContentTypeAction.define_attribute(
                "legal", "region", AttributeType.text, required=False
            ),
        ],
    )
    assert sent["body"]["actions"][0]["inherit_attributes"] is False
    assert sent["body"]["actions"][1]["required"] is False
