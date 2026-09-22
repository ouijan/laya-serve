# Self-contained CPU-only laya-serve, for running the server without a GPU.
#
#   docker build -t laya-serve .
#   docker run -p 127.0.0.1:11500:11500 laya-serve
#
# The english checkpoint is baked in, so the container needs no volume and no
# network to answer. Other checkpoints still download at runtime if asked for;
# mount a volume at HF_HOME to keep them between runs.
#
# CPU only, deliberately. This server is meant to run alongside Ollama and
# leave the card to it; `laya-serve --gpu` on the host covers the GPU case.
#
# The wheel index is why this is 2GB and not ~7GB: plain `pip install torch`
# on Linux drags in the whole CUDA stack.

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

# Downloads the files rather than calling Router.preload, which would load the
# checkpoint through torch. That matters because CI cross-builds arm64 under
# QEMU: fetching files is I/O, running torch under emulation is not.
RUN python -c "\
from huggingface_hub import snapshot_download; \
snapshot_download('convaiinnovations/laya', \
    ignore_patterns=['multilingual/*', 'typed-decisions/*'])"

EXPOSE 11500

# `ok` is false until a checkpoint is actually resident, so a container asked
# for a checkpoint it must first download stays unhealthy until it can serve.
HEALTHCHECK --interval=15s --timeout=5s --start-period=180s --retries=3 \
    CMD ["python", "-c", "import json,sys,urllib.request; \
sys.exit(0 if json.load(urllib.request.urlopen('http://127.0.0.1:11500/health', timeout=4))['ok'] else 1)"]

CMD ["laya-serve", "--cpu"]
