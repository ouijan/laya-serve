"""HTTP surface."""

from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .config import VALID_MODELS, Settings, cuda_name
from .engine import Engine


class PredictRequest(BaseModel):
    state: Dict[str, Any] = Field(..., description="Any dict: text, email, ticket, JSON doc")
    questions: Dict[str, Any] = Field(..., description="Typed questions keyed by name")
    model: str | None = Field(None, description="Force a checkpoint; omit to auto-route")


def create_app(settings: Settings) -> FastAPI:
    engine = Engine(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine.start()
        yield
        engine.stop()

    app = FastAPI(title="laya-serve", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health():
        return {
            "ok": engine.router is not None,
            "models": settings.models,
            "device": engine.device,  # resolved: "cuda" or "cpu"
            "device_requested": settings.device,  # "auto", "cpu" or "cuda"
            "gpu": cuda_name() if engine.device == "cuda" else None,
        }

    @app.post("/predict")
    def predict(req: PredictRequest):
        if req.model and req.model not in VALID_MODELS:
            raise HTTPException(400, f"unknown model '{req.model}'")
        try:
            return engine.predict(req.state, req.questions, req.model)
        except Exception as exc:
            raise HTTPException(500, f"inference failed: {exc}")

    @app.post("/route")
    def route(req: PredictRequest):
        """Routing decision only — no forward pass, sub-millisecond."""
        return engine.route_only(req.state, req.questions)

    return app
