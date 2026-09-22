"""`laya-serve` command line entrypoint."""

import argparse
import logging

from .config import VALID_MODELS, DeviceUnavailable, Settings


def _parse_args() -> argparse.Namespace:
    defaults = Settings()

    parser = argparse.ArgumentParser(prog="laya-serve", description="Serve Laya over HTTP")
    parser.add_argument("--host", default=defaults.host)
    parser.add_argument("--port", type=int, default=defaults.port)

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--cpu",
        dest="device",
        action="store_const",
        const="cpu",
        help="force CPU mode; leaves the GPU entirely to Ollama",
    )
    mode.add_argument(
        "--gpu",
        dest="device",
        action="store_const",
        const="cuda",
        help="force GPU mode; refuses to start if CUDA is unavailable",
    )
    parser.set_defaults(device=defaults.device)

    parser.add_argument(
        "--models",
        default=",".join(defaults.models),
        help=f"comma-separated checkpoints to preload: {', '.join(VALID_MODELS)}",
    )
    parser.add_argument("--log-level", default="info")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = Settings(
        host=args.host,
        port=args.port,
        device=args.device,
        models=[m.strip() for m in args.models.split(",") if m.strip()],
    )
    settings.validate()

    # Fail here rather than deep inside uvicorn's startup.
    try:
        device = settings.resolve_device()
    except DeviceUnavailable as exc:
        raise SystemExit(f"laya-serve: {exc}")
    print(f"laya-serve: {device.upper()} mode, checkpoints {settings.models}")

    import uvicorn

    from .api import create_app

    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
