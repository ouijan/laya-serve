#!/usr/bin/env python3
"""Run the documented example against a live server and print the answers.

This is a demo, not a test: it asserts nothing and needs a running server with
a real checkpoint loaded. Use it to eyeball real model output. The automated
contract tests are in tests/ and need neither.

The payload is pulled from the server's own OpenAPI spec, so what /docs shows
is what this runs.

    laya-serve --cpu --models english &
    python scripts/demo.py [base_url]
"""

import json
import sys
import urllib.request

DEFAULT_URL = "http://127.0.0.1:11500"


def get_json(url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def describe(qid: str, answer: dict) -> str:
    kind = answer["type"]
    if kind == "choice":
        return f"{qid}: {answer['choice']} (confidence {answer['confidence']})"
    if kind == "score":
        top = len(answer["legend"]) - 1
        return f"{qid}: {answer['score']} of {top} (confidence {answer['confidence']})"
    return f"{qid}: {answer['noul']}"


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL

    health = get_json(f"{base}/health")
    print(f"health: ok={health['ok']} device={health['device']} models={health['models']}")

    spec = get_json(f"{base}/openapi.json")
    example = spec["components"]["schemas"]["SystemOneRequest"]["examples"][0]

    result = get_json(f"{base}/v1/systemone", example)
    routing = result.get("routing") or {}
    print(f"model: {result['model']}  usage: {result['usage']['input_tokens']} input tokens")
    print(f"routing: {routing.get('model')} - {routing.get('reason')}")
    for qid, answer in result["answers"].items():
        print(f"  {describe(qid, answer)}")

    decision = get_json(f"{base}/v1/route", example)
    print(f"route: {decision.get('model')} - {decision.get('reason')}")


if __name__ == "__main__":
    main()
