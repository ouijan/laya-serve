"""HTTP surface: a native endpoint plus an OpenAI-shaped shim."""

import json
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .config import Settings, cuda_name
from .engine import Engine

MODEL_ALIASES = {
    "laya": "english",
    "laya-english": "english",
    "laya-multilingual": "multilingual",
    "laya-typed-decisions": "typed-decisions",
    "english": "english",
    "multilingual": "multilingual",
    "typed-decisions": "typed-decisions",
}


class PredictRequest(BaseModel):
    state: Dict[str, Any] = Field(..., description="Any dict: text, email, ticket, JSON doc")
    questions: Dict[str, Any] = Field(..., description="Typed questions keyed by name")
    model: Optional[str] = Field(None, description="Force a checkpoint; omit to auto-route")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "laya"
    messages: List[ChatMessage]


def create_app(settings: Settings) -> FastAPI:
    engine = Engine(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine.start()
        yield
        engine.stop()

    app = FastAPI(title="laya-serve", version="0.1.0", lifespan=lifespan)

    def auth(authorization: Optional[str] = Header(None)) -> None:
        if not settings.api_key:
            return
        expected = f"Bearer {settings.api_key}"
        if authorization != expected:
            raise HTTPException(401, "invalid or missing bearer token")

    @app.get("/health")
    def health():
        return {
            "ok": engine.router is not None,
            "models": settings.models,
            "device": engine.device,  # resolved: "cuda" or "cpu"
            "device_requested": settings.device,  # "auto", "cpu" or "cuda"
            "gpu": cuda_name() if engine.device == "cuda" else None,
            "dtype": engine.dtype,
        }

    @app.post("/predict", dependencies=[Depends(auth)])
    def predict(req: PredictRequest):
        model = MODEL_ALIASES.get(req.model) if req.model else None
        if req.model and model is None:
            raise HTTPException(400, f"unknown model '{req.model}'")
        try:
            return engine.predict(req.state, req.questions, model)
        except Exception as exc:
            raise HTTPException(500, f"inference failed: {exc}")

    @app.post("/route", dependencies=[Depends(auth)])
    def route(req: PredictRequest):
        """Routing decision only — no forward pass, sub-millisecond."""
        return engine.route_only(req.state, req.questions)

    # --- OpenAI-shaped shim -------------------------------------------------
    # Send a user message whose content is JSON: {"state": ..., "questions": ...}
    # Get the answers back as JSON in the assistant message content.

    @app.get("/v1/models", dependencies=[Depends(auth)])
    def list_models():
        return {
            "object": "list",
            "data": [
                {"id": f"laya-{m}", "object": "model", "owned_by": "convaiinnovations"}
                for m in settings.models
            ],
        }

    @app.post("/v1/chat/completions", dependencies=[Depends(auth)])
    def chat_completions(req: ChatRequest):
        user = [m for m in req.messages if m.role == "user"]
        if not user:
            raise HTTPException(400, "no user message")
        try:
            payload = json.loads(user[-1].content)
            state = payload["state"]
            questions = payload["questions"]
        except Exception as exc:
            raise HTTPException(
                400, f"user content must be JSON with 'state' and 'questions': {exc}"
            )

        result = engine.predict(state, questions, MODEL_ALIASES.get(req.model))
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": json.dumps(result)},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    return app
