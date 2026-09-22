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

| Method | Path                   | Purpose                                      |
| ------ | ---------------------- | -------------------------------------------- |
| GET    | `/health`              | Readiness, resident checkpoints, device       |
| POST   | `/predict`             | Native inference — use this one               |
| POST   | `/route`               | Routing decision only, no forward pass        |

Interactive docs at `http://host:11500/docs`.

## Calling it from TypeScript

Use the generated client in [`clients/typescript`](clients/typescript) 
types come from this server's OpenAPI spec, so they can't drift:

```ts
import { createLayaClient } from "@ouijan/laya-client";

const laya = createLayaClient({ baseUrl: "http://your-box:11500" });
const { answers, routing } = await laya.predict({ state, questions });
```

Regenerate after changing an endpoint with `cd clients/typescript && bun run build`.

A fuller example:

```ts
const { answers } = await laya.predict({
  state: { subject: "Duplicate charge", body: "We were billed twice for March." },
  questions: {
    department: {
      type: "choice",
      instructions: "Which department should handle this?",
      criteria: { billing: "invoices, refunds", technical: "bugs", other: "everything else" },
    },
    churn_risk: { type: "noul", instructions: "Does the user threaten to leave?" },
  },
});

console.log(answers.department);
```

`answers` is `Record<string, unknown>`: its shape follows the questions you
send, so the server can't describe it in the spec. Narrow it at the call site.
Everything else is fully typed.

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

## Caveats

- No auth, no TLS. Localhost or behind a reverse proxy.
- Single process, no batching queue. Concurrent requests serialise on the GPU.
  Fine for low-hundreds of req/min; put a queue in front if you need more.
- Base checkpoints score near chance on typed decisions zero-shot. Fine-tune
  before trusting the numbers.
