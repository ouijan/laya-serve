"""Contract tests: the response envelope, per-type answer shapes, validation."""

import pytest

from laya_serve.api import EXAMPLE_REQUEST, NoulAnswer

SYSTEMONE = "/v1/systemone"


def test_health_reports_resolved_device(client):
    body = client.get("/health").json()
    assert body == {
        "ok": True,
        "models": ["english"],
        "device": "cpu",
        "device_requested": "cpu",
        "gpu": None,
    }


def test_returns_typesafe_envelope(client):
    response = client.post(SYSTEMONE, json=EXAMPLE_REQUEST)
    assert response.status_code == 200

    body = response.json()
    assert set(body) >= {"model", "answers", "usage"}
    assert body["usage"] == {"input_tokens": 201, "output_tokens": 0}
    assert set(body["answers"]) == set(EXAMPLE_REQUEST["questions"])


def test_answers_keep_their_question_ids(client):
    answers = client.post(SYSTEMONE, json=EXAMPLE_REQUEST).json()["answers"]
    assert answers["department"]["type"] == "choice"
    assert answers["frustration"]["type"] == "score"
    assert answers["churn_risk"]["type"] == "noul"


def test_choice_answer_shape(client):
    answers = client.post(SYSTEMONE, json=EXAMPLE_REQUEST).json()["answers"]
    choice = answers["department"]
    options = set(EXAMPLE_REQUEST["questions"]["department"]["criteria"])

    assert choice["choice"] in options
    assert set(choice["probabilities"]) == options
    assert 0.0 <= choice["confidence"] <= 1.0


def test_score_answer_carries_legend(client):
    answers = client.post(SYSTEMONE, json=EXAMPLE_REQUEST).json()["answers"]
    score = answers["frustration"]
    levels = EXAMPLE_REQUEST["questions"]["frustration"]["criteria"]

    assert score["legend"] == {str(i): level for i, level in enumerate(levels)}
    assert set(score["probabilities"]) == set(score["legend"])
    assert 0.0 <= score["score"] <= len(levels) - 1


def test_noul_answer_is_a_probability(client):
    answers = client.post(SYSTEMONE, json=EXAMPLE_REQUEST).json()["answers"]
    assert 0.0 <= answers["churn_risk"]["noul"] <= 1.0


def test_noul_confidence_is_required(client):
    """Optional would make every client null-check a value laya always sends."""
    answers = client.post(SYSTEMONE, json=EXAMPLE_REQUEST).json()["answers"]
    assert isinstance(answers["churn_risk"]["confidence"], float)

    schema = NoulAnswer.model_json_schema()
    assert "confidence" in schema["required"]


def test_laya_extras_survive_the_response_model(client):
    """The superset we deliberately keep over Jev's fields."""
    body = client.post(SYSTEMONE, json=EXAMPLE_REQUEST).json()

    assert body["routing"]["model"] == "english"
    assert body["answers"]["department"]["action"]["act_probability"] == 1.0
    assert body["answers"]["churn_risk"]["confidence"] == 0.9086


@pytest.mark.parametrize(
    "state",
    [
        "Billed twice for March.",
        {"subject": "Duplicate charge", "body": "Billed twice."},
        [{"from": "customer", "text": "Billed twice."}],
    ],
    ids=["string", "object", "turns"],
)
def test_state_accepts_string_object_and_turns(client, state):
    payload = {"state": state, "questions": {"q": {"type": "noul", "instructions": "Urgent?"}}}
    assert client.post(SYSTEMONE, json=payload).status_code == 200


def test_routing_hints_reach_the_router(client, router):
    payload = {**EXAMPLE_REQUEST, "model": "multilingual", "lang": "ru"}
    client.post(SYSTEMONE, json=payload)

    call = router.calls[-1]
    assert call["model"] == "multilingual"
    assert call["lang"] == "ru"
    # Unset hints are dropped rather than passed as None.
    assert "task" not in call


def test_rejects_unknown_model(client):
    response = client.post(SYSTEMONE, json={**EXAMPLE_REQUEST, "model": "nope"})
    assert response.status_code == 422


def test_rejects_unknown_question_type(client):
    payload = {"state": "x", "questions": {"q": {"type": "essay", "instructions": "Why?"}}}
    assert client.post(SYSTEMONE, json=payload).status_code == 422


def test_rejects_question_without_instructions(client):
    payload = {"state": "x", "questions": {"q": {"type": "noul"}}}
    assert client.post(SYSTEMONE, json=payload).status_code == 422


def test_route_skips_inference(client, router):
    body = client.post("/v1/route", json=EXAMPLE_REQUEST).json()
    assert body["model"] == "english"
    assert body["reason"]


def test_inference_failure_is_a_500(client, router):
    def explode(*args, **kwargs):
        raise RuntimeError("out of memory")

    router.predict = explode
    response = client.post(SYSTEMONE, json=EXAMPLE_REQUEST)
    assert response.status_code == 500
    assert "out of memory" in response.json()["detail"]
