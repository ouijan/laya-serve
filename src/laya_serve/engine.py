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

    def predict(self, state: Any, questions: Dict[str, Any], **routing: Any) -> Dict[str, Any]:
        """Pass laya's payload straight through.

        laya already returns the System One envelope (model, answers, usage)
        plus a routing key, so reshaping here would only lose fields.
        """
        selected = {k: v for k, v in routing.items() if v is not None}
        return self._require_router().predict(state, questions, **selected)

    def route_only(self, state: Any, questions: Dict[str, Any], **routing: Any) -> Dict[str, Any]:
        """Which checkpoint would handle this, without a forward pass."""
        selected = {k: v for k, v in routing.items() if v is not None}
        return dict(self._require_router().route(state, questions, **selected))

    def stop(self) -> None:
        if self.router is None:
            return
        try:
            self.router.unload()
        finally:
            self.router = None
