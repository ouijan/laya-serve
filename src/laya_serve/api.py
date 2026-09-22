"""HTTP surface, shaped to match TypeSafe's System One API.

The request and response bodies follow https://docs.typesafe.ai so the same
client code works against either. laya returns a few fields Jev does not
(`routing`, per-answer `action`, `confidence` on noul); those are kept as a
superset, since strict clients ignore unknown fields.
"""

from contextlib import asynccontextmanager
from typing import Annotated, Any, Dict, List, Literal, Union

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .config import ModelName, Settings, cuda_name
from .engine import Engine

# Pre-fills "Try it out" at /docs. A real payload: it runs unedited.
EXAMPLE_REQUEST = {
    "state": (
        "Hi, we were billed twice for March and I've had no reply in 3 days. "
        "If this isn't fixed we'll move to a competitor."
    ),
    "questions": {
        "department": {
            "type": "choice",
            "instructions": "Which team should handle this?",
            "criteria": {
                "billing": "Payment or subscription issues",
                "technical": "Bugs or integration problems",
                "sales": "Pricing or account questions",
            },
        },
        "frustration": {
            "type": "score",
            "instructions": "How frustrated the customer appears",
            "criteria": [
                "Calm, just stating facts",
                "Frustrated but civil",
                "Very angry, strong language",
            ],
        },
        "churn_risk": {
            "type": "noul",
            "instructions": "The customer threatens to leave for a competitor",
        },
    },
}

# str | dict | list, matching laya's Agent.system_one and Jev's `state`.
State = Union[str, Dict[str, Any], List[Any]]


class Question(BaseModel):
    """One typed question. Shape is identical to Jev's."""

    type: Literal["choice", "score", "noul"]
    instructions: Any = Field(..., description="The judgement to make; a string, object or list")
    criteria: Dict[str, str] | List[str] | None = Field(
        None,
        description=(
            "choice: {option: meaning}. score: ordered levels, low to high. "
            "noul: optional clarification of yes and no."
        ),
    )

    model_config = {"extra": "allow"}


class SystemOneRequest(BaseModel):
    state: State = Field(..., description="Text, JSON object, or conversation turns")
    questions: Dict[str, Question] = Field(
        ..., description="Typed questions keyed by the id you want back in `answers`"
    )
    model: ModelName | None = Field(None, description="Force a checkpoint; omit to auto-route")
    task: str | None = Field(None, description="Routing hint, e.g. 'typed-decisions'")
    lang: str | None = Field(None, description="Routing hint, e.g. 'en'; otherwise detected")

    model_config = {
        "extra": "allow",
        "protected_namespaces": (),
        "json_schema_extra": {"examples": [EXAMPLE_REQUEST]},
    }


class Action(BaseModel):
    """laya extra: how strongly the model would act on this answer."""

    act_probability: float

    model_config = {"extra": "allow"}


class ChoiceAnswer(BaseModel):
    type: Literal["choice"]
    choice: str = Field(..., description="The selected option key")
    probabilities: Dict[str, float] = Field(..., description="Distribution over your options")
    confidence: float = Field(..., description="How peaked the distribution is, 0-1")
    action: Action | None = None


class ScoreAnswer(BaseModel):
    type: Literal["score"]
    score: float = Field(..., description="Position along your levels; may fall between two")
    legend: Dict[str, str] = Field(..., description="Your levels, keyed by index")
    probabilities: Dict[str, float] = Field(..., description="Distribution over levels")
    confidence: float
    action: Action | None = None


class NoulAnswer(BaseModel):
    type: Literal["noul"]
    noul: float = Field(..., description="Probability the statement is true, 0-1")
    # laya extra; Jev's noul has no confidence.
    confidence: float | None = None
    action: Action | None = None


Answer = Annotated[
    Union[ChoiceAnswer, ScoreAnswer, NoulAnswer],
    Field(discriminator="type"),
]


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int


class Routing(BaseModel):
    """laya extra: which checkpoint served the request, and why."""

    model: str | None = None
    reason: str | None = None

    model_config = {"extra": "allow", "protected_namespaces": ()}


class SystemOneResponse(BaseModel):
    model: str = Field(..., description="The checkpoint that answered")
    answers: Dict[str, Answer]
    usage: Usage
    routing: Routing | None = None

    model_config = {"protected_namespaces": ()}


class HealthResponse(BaseModel):
    ok: bool
    models: List[str]
    device: str | None = Field(None, description='Resolved: "cuda" or "cpu"')
    device_requested: str = Field(..., description='"auto", "cpu" or "cuda"')
    gpu: str | None = None


def create_app(settings: Settings) -> FastAPI:
    engine = Engine(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine.start()
        yield
        engine.stop()

    app = FastAPI(title="laya-serve", version="0.1.0", lifespan=lifespan)

    @app.get("/health", response_model=HealthResponse)
    def health():
        return {
            "ok": engine.router is not None,
            "models": settings.models,
            "device": engine.device,
            "device_requested": settings.device,
            "gpu": cuda_name() if engine.device == "cuda" else None,
        }

    @app.post("/v1/systemone", response_model=SystemOneResponse)
    def system_one(req: SystemOneRequest):
        questions = {k: q.model_dump(exclude_none=True) for k, q in req.questions.items()}
        try:
            return engine.predict(
                req.state, questions, model=req.model, task=req.task, lang=req.lang
            )
        except Exception as exc:
            raise HTTPException(500, f"inference failed: {exc}")

    @app.post("/v1/route", response_model=Routing)
    def route(req: SystemOneRequest):
        """Routing decision only — no forward pass, sub-millisecond."""
        questions = {k: q.model_dump(exclude_none=True) for k, q in req.questions.items()}
        return engine.route_only(
            req.state, questions, model=req.model, task=req.task, lang=req.lang
        )

    return app
