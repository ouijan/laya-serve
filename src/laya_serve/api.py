"""HTTP surface."""

from contextlib import asynccontextmanager
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .config import VALID_MODELS, Settings, cuda_name
from .engine import Engine


class PredictRequest(BaseModel):
    state: Dict[str, Any] = Field(..., description="Any dict: text, email, ticket, JSON doc")
    questions: Dict[str, Any] = Field(..., description="Typed questions keyed by name")
    model: str | None = Field(None, description="Force a checkpoint; omit to auto-route")


# Response models exist so /openapi.json describes what comes back, which is
# what the generated TypeScript client in clients/typescript is built from.


class Routing(BaseModel):
    model: str | None = None
    reason: str | None = None


class PredictResponse(BaseModel):
    # Shaped by the questions you send, so the values stay open.
    answers: Dict[str, Any]
    routing: Routing | None = None


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

    @app.post("/predict", response_model=PredictResponse)
    def predict(req: PredictRequest):
        if req.model and req.model not in VALID_MODELS:
            raise HTTPException(400, f"unknown model '{req.model}'")
        try:
            return engine.predict(req.state, req.questions, req.model)
        except Exception as exc:
            raise HTTPException(500, f"inference failed: {exc}")

    @app.post("/route", response_model=Routing)
    def route(req: PredictRequest):
        """Routing decision only — no forward pass, sub-millisecond."""
        return engine.route_only(req.state, req.questions)

    return app
