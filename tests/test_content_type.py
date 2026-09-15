"""ContentType.list: parses the taxonomy tree (nested children + attributes)."""

import json

import httpx
import pytest

from lighton import AttributeType, ContentType, LightOn, LightOnConfiguration


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

    for kind in (AttributeType.select, AttributeType.multi_select, "select"):
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


def test_batch_posts_every_action_and_returns_per_action_results():
    actions = [
        {"action": "adopt", "content_types": ["legal"]},
        {
            "action": "define_attribute",
            "content_type_path": "legal",
            "name": "flag",
            "attribute_type": "boolean",
        },
    ]
    client, sent = _writer(
        {
            "results": [
                {"status": 201, "data": {"path": "legal"}},
                {"status": 201, "data": {"name": "flag"}},
            ]
        }
    )

    results = ContentType.batch(client, actions)

    assert sent["path"] == "/api/v3/content-types/batch"
    assert sent["body"] == {"actions": actions}
    assert [r["status"] for r in results] == [201, 201]
    assert results[1]["data"]["name"] == "flag"


def test_define_omits_what_you_did_not_set():
    client, sent = _writer({"path": "x", "code": "x", "label": "X"})
    ContentType.define(client, "x", "X")
    assert sent["body"] == {"action": "define_content_type", "code": "x", "label": "X"}
