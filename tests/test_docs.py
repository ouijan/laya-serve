"""Guards on the published spec: the /docs example runs, and the committed
openapi.json the TypeScript client is generated from is not stale.
"""

import json
from pathlib import Path

from laya_serve.api import EXAMPLE_REQUEST, SystemOneRequest, create_app
from laya_serve.config import Settings

COMMITTED_SPEC = Path(__file__).resolve().parents[1] / "clients/typescript/openapi.json"


def build_spec() -> dict:
    return create_app(Settings()).openapi()


def test_docs_example_is_a_valid_request():
    """What Swagger pre-fills must be accepted, not just illustrative."""
    SystemOneRequest.model_validate(EXAMPLE_REQUEST)


def test_spec_publishes_the_example():
    schema = build_spec()["components"]["schemas"]["SystemOneRequest"]
    assert schema["examples"] == [EXAMPLE_REQUEST]


def test_docs_example_actually_runs(client):
    assert client.post("/v1/systemone", json=EXAMPLE_REQUEST).status_code == 200


def test_model_is_an_enum_not_a_free_string():
    """Otherwise /docs pre-fills "string", which fails validation."""
    schema = build_spec()["components"]["schemas"]["SystemOneRequest"]
    variants = schema["properties"]["model"]["anyOf"]
    enums = [v["enum"] for v in variants if "enum" in v]
    assert enums == [["english", "multilingual", "typed-decisions"]]


def test_responses_are_described():
    """An empty response schema would generate an untyped client."""
    paths = build_spec()["paths"]
    for path, method in (("/v1/systemone", "post"), ("/v1/route", "post"), ("/health", "get")):
        content = paths[path][method]["responses"]["200"]["content"]["application/json"]
        assert content["schema"], f"{method.upper()} {path} has no response schema"


def test_committed_spec_matches_the_code():
    """Fails when an endpoint changed without `bun run build`."""
    committed = json.loads(COMMITTED_SPEC.read_text())
    assert committed == json.loads(json.dumps(build_spec(), sort_keys=True)), (
        "clients/typescript/openapi.json is stale; "
        "run `cd clients/typescript && bun run build`"
    )
