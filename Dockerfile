# CPU-only laya-serve. Leaves the GPU entirely to Ollama.
#
#   docker build -t laya-serve .                      # weights on a volume
#   docker build -t laya-serve:baked --target baked . # weights in the image
#
# Docker builds the last stage by default, so the cheap variant is last and
# the baked one is opt-in via --target.
#
# CPU only, deliberately. This server is meant to run alongside Ollama and
# leave the card to it; `laya-serve --gpu` on the host covers the GPU case.
#
# The wheel index is why the image is 1.15GB and not ~6GB: plain
# `pip install torch` on Linux drags in the whole CUDA stack.

ARG PYTHON_VERSION=3.13

FROM python:${PYTHON_VERSION}-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /build
RUN uv venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv

# Its own layer: torch is the slowest part of the build and changes least.
RUN uv pip install --index-url https://download.pytorch.org/whl/cpu torch

COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN uv pip install .


FROM python:${PYTHON_VERSION}-slim AS runtime

# HF_HOME is where checkpoints land. Mount a volume here to keep them between
# runs, or use the `baked` target to bake them in.
ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    HF_HOME=/var/cache/huggingface \
    PYTHONUNBUFFERED=1 \
    LAYA_HOST=0.0.0.0 \
    LAYA_DEVICE=cpu \
    LAYA_MODELS=english

COPY --from=builder /opt/venv /opt/venv

RUN useradd --create-home --uid 10001 laya \
    && mkdir -p "$HF_HOME" \
    && chown -R laya:laya "$HF_HOME"

USER laya
EXPOSE 11500

# `ok` is false until a checkpoint is actually resident, so the container is
# unhealthy while the first download runs rather than healthy-but-useless.
HEALTHCHECK --interval=15s --timeout=5s --start-period=180s --retries=3 \
    CMD ["python", "-c", "import json,sys,urllib.request; \
sys.exit(0 if json.load(urllib.request.urlopen('http://127.0.0.1:11500/health', timeout=4))['ok'] else 1)"]

CMD ["laya-serve", "--cpu"]


# Weights in the image: starts offline in seconds, no volume needed.
#
# Downloads the files rather than calling Router.preload, which would load the
# checkpoint through torch. That matters when this stage is cross-built under
# QEMU in CI: fetching files is I/O, running torch under emulation is not.
FROM runtime AS baked

RUN python -c "\
from huggingface_hub import snapshot_download; \
snapshot_download('convaiinnovations/laya', \
    ignore_patterns=['multilingual/*', 'typed-decisions/*'])"


# Last stage wins when --target is omitted, so plain `docker build .` gets the
# ~1.2GB image rather than accidentally downloading 614MB of weights.
FROM runtime AS default
