"""Settings, all overridable by environment variable or CLI flag."""

import os
from dataclasses import dataclass, field
from typing import List, Optional

VALID_MODELS = ("english", "multilingual", "typed-decisions")


def _env_list(name: str, default: List[str]) -> List[str]:
    raw = os.environ.get(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


class DeviceUnavailable(RuntimeError):
    """Raised when GPU mode was asked for explicitly and CUDA isn't there."""


def cuda_available() -> bool:
    try:
        import torch

        return torch.cuda.is_available()
    except Exception:
        return False


def cuda_name() -> Optional[str]:
    try:
        import torch

        return torch.cuda.get_device_name(0)
    except Exception:
        return None


@dataclass
class Settings:
    host: str = os.environ.get("LAYA_HOST", "127.0.0.1")
    port: int = int(os.environ.get("LAYA_PORT", "11500"))

    # "cuda", "cpu", or "auto" to pick GPU when one is present.
    device: str = os.environ.get("LAYA_DEVICE", "auto")

    # Which checkpoints to hold resident. Fewer = less VRAM.
    models: List[str] = field(
        default_factory=lambda: _env_list("LAYA_MODELS", ["english", "multilingual"])
    )

    # "half" tries fp16 on the loaded weights, "full" leaves them as-is.
    dtype: str = os.environ.get("LAYA_DTYPE", "half")

    # If set, every request must send `Authorization: Bearer <key>`.
    api_key: Optional[str] = os.environ.get("LAYA_API_KEY") or None

    def validate(self) -> None:
        bad = [m for m in self.models if m not in VALID_MODELS]
        if bad:
            raise ValueError(
                f"unknown checkpoint(s) {bad}; valid: {', '.join(VALID_MODELS)}"
            )
        if self.dtype not in ("half", "full"):
            raise ValueError("dtype must be 'half' or 'full'")
        if self.device not in ("auto", "cpu", "cuda"):
            raise ValueError("device must be 'auto', 'cpu' or 'cuda'")

    def resolve_device(self) -> str:
        """Turn 'auto' into a concrete device. Fails loudly on explicit --gpu."""
        if self.device == "cuda":
            if not cuda_available():
                raise DeviceUnavailable(
                    "GPU mode requested but torch.cuda.is_available() is False. "
                    "Check the driver and the CUDA build of torch, or run with --cpu."
                )
            return "cuda"
        if self.device == "cpu":
            return "cpu"
        return "cuda" if cuda_available() else "cpu"

    def resolve_dtype(self, device: str) -> str:
        """fp16 on CPU is slow or unimplemented for many ops — force full there."""
        if device == "cpu" and self.dtype == "half":
            return "full"
        return self.dtype
