"""Owns the laya Router for the process lifetime."""

import logging
from typing import Any, Dict, Optional

from .config import Settings, cuda_name

log = logging.getLogger("laya_serve")


def _to_half(obj: Any) -> bool:
    """Best-effort fp16 cast. Returns True if anything was actually cast.

    laya doesn't document a dtype knob, so this walks one level of attributes
    looking for torch Modules. If the internals change this quietly does
    nothing, which is why it logs the outcome.
    """
    try:
        import torch
    except ImportError:
        return False

    cast = False
    for name in dir(obj):
        if name.startswith("__"):
            continue
        try:
            attr = getattr(obj, name)
        except Exception:
            continue
        if isinstance(attr, torch.nn.Module):
            attr.half()
            cast = True
    return cast


class Engine:
    def __init__(self, settings: Settings):
        settings.validate()
        self.settings = settings
        self.router = None
        # Filled in by start(): what we actually ended up running on.
        self.device: Optional[str] = None
        self.dtype: Optional[str] = None

    def start(self) -> None:
        from laya import Router

        # Raises DeviceUnavailable if --gpu was explicit and CUDA is missing.
        self.device = self.settings.resolve_device()
        self.dtype = self.settings.resolve_dtype(self.device)

        if self.device == "cuda":
            log.info("GPU mode on %s", cuda_name() or "unknown CUDA device")
        else:
            reason = (
                "requested" if self.settings.device == "cpu" else "no CUDA device found"
            )
            log.info("CPU mode (%s) — expect ~200-460ms per request", reason)

        if self.dtype != self.settings.dtype:
            log.info("dtype downgraded to 'full': fp16 is not worth it on CPU")

        kwargs: Dict[str, Any] = {
            "max_loaded": len(self.settings.models),
            "device": self.device,
        }
        log.info("building router (%s)", kwargs)
        self.router = Router(**kwargs)

        log.info("preloading %s", self.settings.models)
        self.router.preload(self.settings.models)

        if self.dtype == "half":
            if _to_half(self.router):
                log.info("cast resident weights to fp16")
            else:
                log.warning(
                    "fp16 cast found no torch modules on Router; "
                    "weights are still full precision"
                )

    def predict(
        self,
        state: Dict[str, Any],
        questions: Dict[str, Any],
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self.router is None:
            raise RuntimeError("engine not started")
        kwargs = {"model": model} if model else {}
        result = self.router.predict(state, questions, **kwargs)
        return {"answers": result["answers"], "routing": result.get("routing")}

    def route_only(self, state: Dict[str, Any], questions: Dict[str, Any]) -> Dict[str, Any]:
        """Which checkpoint would handle this, without a forward pass."""
        decision = self.router.route(state, questions)
        return {"model": getattr(decision, "model", None), "reason": decision.reason}

    def stop(self) -> None:
        if self.router is None:
            return
        try:
            self.router.unload()
        finally:
            if self.device == "cuda":
                try:
                    import torch

                    torch.cuda.empty_cache()
                except Exception:
                    pass
            self.router = None
