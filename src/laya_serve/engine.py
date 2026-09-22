"""Owns the laya Router for the process lifetime."""

import logging
from typing import Any, Dict

from .config import Settings, cuda_name

log = logging.getLogger("laya_serve")


class Engine:
    def __init__(self, settings: Settings):
        settings.validate()
        self.settings = settings
        self.router = None
        # Filled in by start(): what we actually ended up running on.
        self.device: str | None = None

    def start(self) -> None:
        from laya import Router

        # Raises DeviceUnavailable if --gpu was explicit and CUDA is missing.
        self.device = self.settings.resolve_device()
        if self.device == "cuda":
            log.info("GPU mode on %s", cuda_name() or "unknown CUDA device")
        else:
            log.info("CPU mode — expect ~200-460ms per request")

        self.router = Router(max_loaded=len(self.settings.models), device=self.device)
        log.info("preloading %s", self.settings.models)
        self.router.preload(self.settings.models)

    def _require_router(self):
        if self.router is None:
            raise RuntimeError("engine not started")
        return self.router

    def predict(
        self,
        state: Dict[str, Any],
        questions: Dict[str, Any],
        model: str | None = None,
    ) -> Dict[str, Any]:
        kwargs = {"model": model} if model else {}
        result = self._require_router().predict(state, questions, **kwargs)
        return {"answers": result["answers"], "routing": result.get("routing")}

    def route_only(self, state: Dict[str, Any], questions: Dict[str, Any]) -> Dict[str, Any]:
        """Which checkpoint would handle this, without a forward pass."""
        decision = self._require_router().route(state, questions)
        return {"model": getattr(decision, "model", None), "reason": decision.reason}

    def stop(self) -> None:
        if self.router is None:
            return
        try:
            self.router.unload()
        finally:
            self.router = None
