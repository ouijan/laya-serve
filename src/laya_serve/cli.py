"""`laya-serve` command line entrypoint."""

import argparse
import logging

from .config import VALID_MODELS, DeviceUnavailable, Settings


def main() -> None:
    defaults = Settings()

    p = argparse.ArgumentParser(prog="laya-serve", description="Serve Laya over HTTP")
    p.add_argument("--host", default=defaults.host)
    p.add_argument("--port", type=int, default=defaults.port)
    mode = p.add_mutually_exclusive_group()
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
    mode.add_argument(
        "--device",
        dest="device",
        choices=("auto", "cpu", "cuda"),
        help="explicit form of --cpu/--gpu (default: auto)",
    )
    p.set_defaults(device=defaults.device)
    p.add_argument(
        "--models",
        default=",".join(defaults.models),
        help=f"comma-separated checkpoints to preload: {', '.join(VALID_MODELS)}",
    )
    p.add_argument("--dtype", choices=("half", "full"), default=defaults.dtype)
    p.add_argument("--api-key", default=defaults.api_key, help="require this bearer token")
    p.add_argument("--log-level", default="info")
    args = p.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = Settings(
        host=args.host,
        port=args.port,
        device=args.device,
        models=[m.strip() for m in args.models.split(",") if m.strip()],
        dtype=args.dtype,
        api_key=args.api_key,
    )
    settings.validate()

    # Fail here rather than deep inside uvicorn's startup.
    try:
        device = settings.resolve_device()
    except DeviceUnavailable as exc:
        p.exit(2, f"laya-serve: {exc}\n")
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
