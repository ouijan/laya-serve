"""Test fixtures.

The engine is stubbed so the suite needs no checkpoint download and no GPU.
FakeRouter returns the same shapes laya does; the payloads below were recorded
from a real `english` run, so a change in laya's output shape shows up as a
failure here rather than in production.
"""

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from laya_serve import engine as engine_module
from laya_serve.api import create_app
from laya_serve.config import Settings


def _answer_for(question: Dict[str, Any]) -> Dict[str, Any]:
    """Mimic laya's per-type answer shape, including its extras."""
    action = {"act_probability": 1.0}
    criteria = question.get("criteria") or {}

    if question["type"] == "choice":
        options = list(criteria)
        even = round(1.0 / len(options), 4) if options else 0.0
        return {
            "type": "choice",
            "choice": options[0] if options else "",
            "probabilities": {option: even for option in options},
            "confidence": 0.8375,
            "action": action,
        }

    if question["type"] == "score":
        levels = list(criteria)
        return {
            "type": "score",
            "score": 1.466,
            "legend": {str(i): level for i, level in enumerate(levels)},
            "probabilities": {str(i): round(1.0 / len(levels), 4) for i in range(len(levels))},
            "confidence": 0.31,
            "action": action,
        }

    return {"type": "noul", "noul": 0.9086, "confidence": 0.9086, "action": action}


class FakeRouter:
    """Records what it was called with, so routing passthrough is assertable."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def predict(self, state: Any, questions: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        self.calls.append({"state": state, "questions": questions, **kwargs})
        return {
            "model": "laya-rl-agent",
            "answers": {qid: _answer_for(q) for qid, q in questions.items()},
            "usage": {"input_tokens": 201, "output_tokens": 0},
            "routing": {
                "model": "english",
                "reason": "English Latin text",
                "repo": "convaiinnovations/laya",
            },
        }

    def route(self, state: Any, questions: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        self.calls.append({"state": state, "questions": questions, **kwargs})
        return {"model": "english", "reason": "English Latin text"}

    def preload(self, models: list[str]) -> None:
        pass

    def unload(self) -> None:
        pass


@pytest.fixture
def router(monkeypatch: pytest.MonkeyPatch) -> FakeRouter:
    fake = FakeRouter()

    def fake_start(self: engine_module.Engine) -> None:
        self.device = "cpu"
        self.router = fake

    monkeypatch.setattr(engine_module.Engine, "start", fake_start)
    return fake


@pytest.fixture
def settings() -> Settings:
    return Settings(device="cpu", models=["english"])


@pytest.fixture
def client(router: FakeRouter, settings: Settings):
    # The context manager runs lifespan, so the stubbed start() is applied.
    with TestClient(create_app(settings)) as test_client:
        yield test_client
