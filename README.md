# laya-serve

A slim HTTP wrapper around [Laya](https://github.com/NandhaKishorM/laya) so remote
apps can call it over the network. Runs alongside Ollama on the same box.

## Install

Needs Python 3.10–3.13 (torch has no 3.14 wheels yet). Install into a virtual
environment — a Homebrew Python will refuse a system-wide install (PEP 668).

```bash
cd laya-serve
uv venv --python 3.13
uv pip install -e .
```

Without `uv`, the stdlib equivalent:

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e .
```

## Run

Either activate the venv (`source .venv/bin/activate`) or call the script
directly as `./.venv/bin/laya-serve`.

```bash
# Defaults: 127.0.0.1:11500, auto device, english + multilingual, fp16 on GPU
laya-serve

# Require a token on the LAN
laya-serve --host 0.0.0.0 --api-key hunter2
```

### Run modes

| Flag               | Behaviour                                                        |
| ------------------ | ---------------------------------------------------------------- |
| *(none)* / `--device auto` | GPU if CUDA is present, otherwise CPU. Never fails.        |
| `--gpu`            | GPU only. **Refuses to start** if CUDA is unavailable.            |
| `--cpu`            | CPU only. Leaves the card entirely to Ollama.                     |

```bash
# Share the GPU politely with Ollama: one checkpoint, half precision
laya-serve --host 0.0.0.0 --gpu --models english --dtype half

# Zero VRAM contention — slower (~200-460ms) but the card stays free
laya-serve --host 0.0.0.0 --cpu
```

`--gpu` failing loudly is the point: on `auto`, a driver hiccup or a CPU-only
torch wheel gets you a server that quietly runs 10x slower. If you meant GPU,
say so and find out at startup.

`--dtype half` is ignored in CPU mode and downgraded to `full`, since fp16 on
CPU is slow or unimplemented for many ops. The log line tells you when this
happens, and `/health` reports what you actually got:

```json
{ "ok": true, "device": "cuda", "device_requested": "auto",
  "gpu": "NVIDIA GeForce RTX 4080", "dtype": "half" }
```

Every flag has an env equivalent: `LAYA_HOST`, `LAYA_PORT`, `LAYA_DEVICE`
(`auto`/`cpu`/`cuda`), `LAYA_MODELS`, `LAYA_DTYPE`, `LAYA_API_KEY`.

## Endpoints

| Method | Path                   | Purpose                                      |
| ------ | ---------------------- | -------------------------------------------- |
| GET    | `/health`              | Readiness, resident checkpoints, device       |
| POST   | `/predict`             | Native inference — use this one               |
| POST   | `/route`               | Routing decision only, no forward pass        |
| GET    | `/v1/models`           | OpenAI-shaped model list                      |
| POST   | `/v1/chat/completions` | OpenAI-shaped shim                            |

Interactive docs at `http://host:11500/docs`.

## Calling it from TypeScript

```ts
type LayaResult = {
  answers: Record<string, any>;
  routing: { model: string; reason: string } | null;
};

export async function decide(state: object, questions: object): Promise<LayaResult> {
  const res = await fetch("http://your-box:11500/predict", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(process.env.LAYA_API_KEY
        ? { Authorization: `Bearer ${process.env.LAYA_API_KEY}` }
        : {}),
    },
    body: JSON.stringify({ state, questions }),
  });
  if (!res.ok) throw new Error(`laya ${res.status}: ${await res.text()}`);
  return res.json();
}

const { answers } = await decide(
  { subject: "Duplicate charge", body: "We were billed twice for March." },
  {
    department: {
      type: "choice",
      instructions: "Which department should handle this?",
      criteria: { billing: "invoices, refunds", technical: "bugs", other: "everything else" },
    },
    churn_risk: { type: "noul", instructions: "Does the user threaten to leave?" },
  },
);

console.log(answers.department.choice, answers.department.confidence);
```

### With the `openai` client

Works, but you're packing JSON into a user message and parsing it back out.
Only worth it if you want one client for both Ollama and this.

```ts
import OpenAI from "openai";

const client = new OpenAI({ baseURL: "http://your-box:11500/v1", apiKey: "unused" });

const completion = await client.chat.completions.create({
  model: "laya-multilingual",
  messages: [{ role: "user", content: JSON.stringify({ state, questions }) }],
});

const { answers } = JSON.parse(completion.choices[0].message.content!);
```

No streaming, no token counts, no real prompt — it's a shape, not a chat model.

## Running as a service

Start it before Ollama so Ollama sizes its GPU offload around the resident
weights. `/etc/systemd/system/laya-serve.service`:

```ini
[Unit]
Description=laya-serve
Before=ollama.service

[Service]
ExecStart=/usr/local/bin/laya-serve --host 0.0.0.0 --gpu --models english --dtype half
Restart=on-failure
User=youruser

[Install]
WantedBy=multi-user.target
```

## Caveats

- The `--dtype half` cast is best-effort: Laya exposes no dtype knob, so the
  engine walks the Router for torch modules and logs whether it found any. If
  it warns, you're running full precision.
- Single process, no batching queue. Concurrent requests serialise on the GPU.
  Fine for low-hundreds of req/min; put a queue in front if you need more.
- Base checkpoints score near chance on typed decisions zero-shot. Fine-tune
  before trusting the numbers.
