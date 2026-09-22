# laya-serve

A slim HTTP wrapper around [Laya](https://github.com/NandhaKishorM/laya) so remote
apps can call it over the network. Runs alongside Ollama on the same box.

## Install

Needs Python 3.10–3.13 (torch has no 3.14 wheels yet). `mise.toml` pins the
interpreter and `uv`, and creates `.venv` on `cd` into the directory.

```bash
cd laya-serve
mise trust
mise install     # fetches python 3.13 + uv, creates .venv
mise run install # uv pip install -e .
```

Without mise, any venv on Python ≤3.13 works. Note a Homebrew Python refuses a
system-wide install (PEP 668), so the venv is not optional:

```bash
uv venv --python 3.13 && uv pip install -e .
# or: python3.13 -m venv .venv && .venv/bin/pip install -e .
```

## Run

With mise activated in your shell, `.venv` is on `PATH` automatically inside
this directory. Otherwise `source .venv/bin/activate` or call
`./.venv/bin/laya-serve` directly.

On Apple Silicon use `--cpu`: the engine only checks `torch.cuda`, so there is
no MPS path and `auto` silently lands on CPU anyway.

```bash
# Defaults: 127.0.0.1:11500, auto device, english + multilingual
laya-serve

# Listen on the LAN
laya-serve --host 0.0.0.0
```

### Run modes

| Flag      | Behaviour                                             |
| --------- | ----------------------------------------------------- |
| *(none)*  | GPU if CUDA is present, otherwise CPU. Never fails.    |
| `--gpu`   | GPU only. **Refuses to start** if CUDA is unavailable. |
| `--cpu`   | CPU only. Leaves the card entirely to Ollama.          |

```bash
# Share the GPU politely with Ollama: one checkpoint only
laya-serve --host 0.0.0.0 --gpu --models english

# Zero VRAM contention — slower (~200-460ms) but the card stays free
laya-serve --host 0.0.0.0 --cpu
```

`--gpu` failing loudly is the point: on `auto`, a driver hiccup or a CPU-only
torch wheel gets you a server that quietly runs 10x slower. If you meant GPU,
say so and find out at startup.

`/health` reports what you actually got:

```json
{ "ok": true, "device": "cuda", "device_requested": "auto",
  "gpu": "NVIDIA GeForce RTX 4080", "models": ["english"] }
```

Every flag has an env equivalent: `LAYA_HOST`, `LAYA_PORT`, `LAYA_DEVICE`
(`auto`/`cpu`/`cuda`), `LAYA_MODELS`.

There is no auth. Bind to `127.0.0.1` (the default), or put it behind something
that has auth. Never expose it to an untrusted network directly.

## Endpoints

| Method | Path            | Purpose                                 |
| ------ | --------------- | --------------------------------------- |
| GET    | `/health`       | Readiness, resident checkpoints, device |
| POST   | `/v1/systemone` | Inference. This is the one you want.    |
| POST   | `/v1/route`     | Routing decision only, no forward pass  |

Interactive docs at `http://host:11500/docs`. The example there is a real
payload: "Try it out" works unedited, and a test asserts that it does.

To see real model output against a running server:

```bash
python scripts/demo.py           # or: python scripts/demo.py http://your-box:11500
```

That's a demo, not a test: it prints and asserts nothing. It reads the example
out of the live server's spec, so what `/docs` shows is what it runs.

### Matching TypeSafe

The request and response bodies follow [TypeSafe's System One API][ts], whose
Jev model shares laya's three primitives (`choice`, `score`, `noul`). Same
`state` + `questions` in, same `{ model, answers, usage }` out.

[ts]: https://docs.typesafe.ai/introduction

laya returns three things Jev has no field for. They're kept as a superset,
since strict clients ignore unknown keys:

| Extra                    | What it gives you                            |
| ------------------------ | -------------------------------------------- |
| `routing`                | Which checkpoint answered, and why           |
| `action.act_probability` | Per answer, how strongly the model would act |
| `confidence` on `noul`   | Jev returns `noul` alone                     |

One known divergence: top-level `model` is laya's internal agent name
(`laya-rl-agent`), not the checkpoint. Use `routing.model` for that.

### Routing

laya bundles three checkpoints and picks one per request without loading
anything. Precedence: `model` > `task` > question ids matching a
typed-decisions workflow > `lang` > detected script/language > default.
`reason` says which rule fired:

```bash
curl -s localhost:11500/v1/route -H 'Content-Type: application/json' \
  -d '{"state":"Здравствуйте, меня дважды списали",
       "questions":{"q":{"type":"noul","instructions":"Billing complaint?"}}}'
# {"model": "multilingual",
#  "reason": "non-Latin script (cyrillic, 100% of letters); ..."}
```

## Calling it from TypeScript

Use the generated client in [`clients/typescript`](clients/typescript) 
types come from this server's OpenAPI spec, so they can't drift:

Type names mirror the TypeSafe SDK, so moving between this and the hosted API
is a change of import rather than of code.

```ts
import { createLayaClient, isChoice } from "@ouijan/laya-client";

const laya = createLayaClient({ baseUrl: "http://your-box:11500" });

const { answers, routing, usage } = await laya.systemOne({
  state: "We were billed twice for March. We'll move to a competitor.",
  questions: {
    department: {
      type: "choice",
      instructions: "Which team should handle this?",
      criteria: { billing: "invoices, refunds", technical: "bugs", sales: "pricing" },
    },
    churn_risk: { type: "noul", instructions: "The customer threatens to leave" },
  },
});

const department = answers.department;
if (isChoice(department)) {
  console.log(department.choice, department.confidence); // "billing" 0.93
}
```

`answers` is a discriminated union on `type`: narrow with `isChoice`, `isScore`
or `isNoul` and the remaining fields follow.

Regenerate after changing an endpoint with `cd clients/typescript && bun run build`.

## Docker

CPU only, so the card stays free for Ollama. There is no GPU image: the
container exists to sit next to Ollama, and `laya-serve --gpu` on the host
covers the GPU case without containerising CUDA.

Two variants from one Dockerfile:

```bash
docker build -t laya-serve .                       # 1.15GB, weights on a volume
docker build -t laya-serve:baked --target baked .  # 2GB, weights in the image
```

CI publishes both to GHCR from `main`, each a manifest list covering amd64
and arm64, so a pull resolves to the right architecture on its own:

```bash
docker pull ghcr.io/ouijan/laya-serve:cpu
docker pull ghcr.io/ouijan/laya-serve:cpu-baked
```

Weights on a volume, downloaded on first boot:

```bash
docker run -d --name laya \
  -p 127.0.0.1:11500:11500 \
  -v laya-models:/var/cache/huggingface \
  laya-serve
```

The baked variant needs no volume and no network:

```bash
docker run -d --network none laya-serve:baked
```

Publish to `127.0.0.1` as above unless you mean to expose it. The container
listens on `0.0.0.0` because it has to, and there is no auth.

`HEALTHCHECK` polls `/health` and only reports healthy once a checkpoint is
resident, so the container stays unhealthy while a first download runs rather
than accepting traffic it can't serve. `start-period` allows 3 minutes.

Configure with the same env vars as the CLI; the image defaults to
`LAYA_DEVICE=cpu` and `LAYA_MODELS=english`:

```bash
docker run -e LAYA_MODELS=english,multilingual laya-serve
```

The CPU wheel index in the Dockerfile is not incidental. A plain
`pip install torch` on Linux pulls ~3GB of CUDA libraries that a CPU image can
never use; the image ships `torch 2.14.0+cpu` and zero `nvidia-*` packages.

## Running as a service

Start it before Ollama so Ollama sizes its GPU offload around the resident
weights. `/etc/systemd/system/laya-serve.service`:

```ini
[Unit]
Description=laya-serve
Before=ollama.service

[Service]
ExecStart=/usr/local/bin/laya-serve --host 0.0.0.0 --gpu --models english
Restart=on-failure
User=youruser

[Install]
WantedBy=multi-user.target
```

## Tests

```bash
uv pip install -e '.[dev]'
pytest
```

22 tests, ~0.1s, no checkpoint download and no GPU: the engine is stubbed with
laya's recorded output shapes. They cover the response envelope, the answer
shape of each question type, the laya extras, `state` as string/object/turns,
routing passthrough, and the 422/500 paths.

Two of them are drift guards rather than behaviour:

- the `/docs` example must be a valid request, and must actually run
- `clients/typescript/openapi.json` must match the code, so the TypeScript
  client cannot be generated from a stale spec

## Caveats

- No auth, no TLS. Localhost or behind a reverse proxy.
- Single process, no batching queue. Concurrent requests serialise on the GPU.
  Fine for low-hundreds of req/min; put a queue in front if you need more.
- Base checkpoints score near chance on typed decisions zero-shot. Fine-tune
  before trusting the numbers.
