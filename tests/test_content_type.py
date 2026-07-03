"""ContentType.list: parses the taxonomy tree (nested children + attributes)."""

import httpx

from lighton import ContentType, LightOn, LightOnConfiguration


def make_client(handler) -> LightOn:
    return LightOn(
        "k", config=LightOnConfiguration(transport=httpx.MockTransport(handler))
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
