# laya-serve

An HTTP server for [Laya](https://github.com/NandhaKishorM/laya), so apps that
aren't Python can use it.

## Why this exists

Laya is a System One decision engine: you give it a state and some typed
questions, it answers all of them in one forward pass — no text generation, so
nothing to parse and nothing to hallucinate. Questions come in three shapes,
`choice`, `score` and `noul`, and answers come back with probabilities and
calibrated confidence.

It ships as a Python library. That's a problem if your application is a
TypeScript service, or if you want one box holding the weights while several
apps call it. This repo puts an HTTP API in front, with:

- a request and response shape matching [TypeSafe's System One API][ts], whose
  Jev model uses the same three primitives, so client code ports between them
- a generated [TypeScript client](clients/typescript) typed from the server's
  own OpenAPI spec
- a CPU-only Docker image, for running it on a machine with no GPU

Laya's `Router` picks between three checkpoints per request based on the
script and language it detects, and that decision is exposed here too.

[ts]: https://docs.typesafe.ai/introduction

## Quickstart

You don't need to clone this repo: the server is a container, the client is on
npm, and neither needs a GPU.

```bash
docker run -d --name laya -p 127.0.0.1:11500:11500 ghcr.io/ouijan/laya-serve
until curl -sf localhost:11500/health >/dev/null; do sleep 2; done
mkdir laya-play && cd laya-play && bun init -y && bun add @ouijan/laya-client
```

That wait is 2-3 minutes on a cold pull and ~30s once the image is local; it
isn't hung. Then `index.ts`:

```ts
import { createLayaClient, isChoice, isNoul } from "@ouijan/laya-client";

const laya = createLayaClient({ baseUrl: "http://localhost:11500" });

const { answers, routing } = await laya.systemOne({
  state:
    "We were billed twice for March and nobody has replied in 3 days. " +
    "If this is not fixed we will move to a competitor.",
  questions: {
    department: {
      type: "choice",
      instructions: "Which team should handle this?",
      criteria: { billing: "payments and refunds", technical: "bugs" },
    },
    churn_risk: {
      type: "noul",
      instructions: "The customer threatens to leave",
    },
  },
});

const { department, churn_risk } = answers;

if (isChoice(department)) console.log(department.choice, department.confidence);
if (isNoul(churn_risk)) console.log(churn_risk.noul, churn_risk.confidence);
console.log(routing?.model, routing?.reason);
```

`bun run index.ts` prints:

```
billing 0.6841
0.8761 0.8761
english English Latin text
```

`answers` is a union discriminated on `type`. Narrow with `isChoice`,
`isScore` or `isNoul` and the remaining fields follow.

The questions are the interesting part — edit `state` and `questions` and run
it again. A fourth question costs nothing, since they're all answered in the
same forward pass and nothing is generated. `docker rm -f laya` stops the
server. Interactive docs are at `http://localhost:11500/docs`, where the
pre-filled example is a real payload you can "Try it out" unedited.

### Have an agent set it up

[`AGENTS.md`](AGENTS.md) is the whole procedure, written for a coding agent.
Point one at it:

```text
Set up a sandbox for me to try Laya, following
https://github.com/ouijan/laya-serve/blob/main/AGENTS.md
```

It will ask what decision you want to make, then run the thing and show you
the output.

## Without TypeScript

It's an HTTP API, so curl is enough:

```bash
curl -s localhost:11500/v1/systemone -H 'Content-Type: application/json' -d '{
  "state": "We were billed twice for March and nobody has replied in 3 days. If this is not fixed we will move to a competitor.",
  "questions": {
    "department": {
      "type": "choice",
      "instructions": "Which team should handle this?",
      "criteria": {"billing": "payments, refunds", "technical": "bugs"}
    },
    "churn_risk": {
      "type": "noul",
      "instructions": "The customer threatens to leave"
    }
  }
}'
```

```json
{
  "model": "laya-rl-agent",
  "answers": {
    "department": {
      "type": "choice",
      "choice": "billing",
      "probabilities": { "billing": 0.9452, "technical": 0.0548 },
      "confidence": 0.6936
    },
    "churn_risk": { "type": "noul", "noul": 0.8761, "confidence": 0.8761 }
  },
  "usage": { "input_tokens": 107, "output_tokens": 0 },
  "routing": { "model": "english", "reason": "English Latin text" }
}
```

(Trimmed: each answer also carries `action.act_probability`, and `routing`
includes the script/language detection behind the decision.)

## Endpoints

| Method | Path            | Purpose                                 |
| ------ | --------------- | --------------------------------------- |
| GET    | `/health`       | Readiness, resident checkpoints, device |
| POST   | `/v1/systemone` | Inference. This is the one you want.    |
| POST   | `/v1/route`     | Routing decision only, no forward pass  |

### Matching TypeSafe

Request and response bodies follow [TypeSafe's System One API][ts]: same
`state` + `questions` in, same `{ model, answers, usage }` out.

Laya returns three things Jev has no field for. They're kept as a superset,
since strict clients ignore unknown keys:

| Extra                    | What it gives you                            |
| ------------------------ | -------------------------------------------- |
| `routing`                | Which checkpoint answered, and why           |
| `action.act_probability` | Per answer, how strongly the model would act |
| `confidence` on `noul`   | Jev returns `noul` alone                     |

One known divergence: top-level `model` is laya's internal agent name
(`laya-rl-agent`), not the checkpoint. Use `routing.model` for that.

### Routing

Laya bundles three checkpoints and picks one per request without loading
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

The English checkpoint scores near zero on non-Latin scripts while staying
confident, so this routing is load-bearing rather than an optimisation. See
the [upstream benchmarks](https://github.com/NandhaKishorM/laya#why-route-the-evidence).

## TypeScript client

[`@ouijan/laya-client`](clients/typescript) is generated from this server's
OpenAPI spec, so the types can't drift from the API. Names mirror the TypeSafe
SDK, so moving between this and the hosted API is a change of import.

`answers` is a discriminated union on `type`: narrow with `isChoice`,
`isScore` or `isNoul` and the remaining fields follow. Non-2xx responses throw
`LayaError`. See the [client README](clients/typescript/README.md) for the
full surface.

## Running it

### Docker

Published from `main` as a manifest list covering amd64 and arm64, so a pull
resolves to the right architecture.

CPU only, deliberately: the container is meant to sit next to Ollama and leave
the card to it. For GPU, run on the host with `--gpu` rather than
containerising CUDA. The CPU wheel index in the Dockerfile is why the image is
2GB and not ~7GB — a plain `pip install torch` on Linux pulls the whole CUDA
stack.

Other checkpoints download at runtime. Mount a volume at `HF_HOME` to keep
them between runs:

```bash
docker run -d -p 127.0.0.1:11500:11500 \
  -e LAYA_MODELS=english,multilingual \
  -v laya-models:/var/cache/huggingface \
  ghcr.io/ouijan/laya-serve
```

`HEALTHCHECK` reports healthy only once a checkpoint is resident, so a
container still downloading one isn't sent traffic it can't serve.

Publish to `127.0.0.1` as above unless you mean to expose it. The container
listens on `0.0.0.0` because it has to, and there is no auth.

### On the host

Needs Python 3.10–3.13 (torch has no 3.14 wheels yet). `mise.toml` pins the
interpreter and `uv`, and creates `.venv` on `cd` into the directory:

```bash
mise trust
mise install      # python 3.13 + uv, creates .venv
mise run install  # uv pip install -e '.[dev]'
mise run serve    # laya-serve --cpu
```

Without mise, any venv on Python ≤3.13 works. A Homebrew Python refuses a
system-wide install (PEP 668), so the venv isn't optional:

```bash
uv venv --python 3.13 && uv pip install -e .
```

`laya-serve` is only on `PATH` inside that venv. Outside a mise shell, call it
as `.venv/bin/laya-serve`.

### Run modes

| Flag      | Behaviour                                             |
| --------- | ----------------------------------------------------- |
| *(none)*  | GPU if CUDA is present, otherwise CPU. Never fails.    |
| `--gpu`   | GPU only. **Refuses to start** if CUDA is unavailable. |
| `--cpu`   | CPU only. Leaves the card entirely to Ollama.          |

`--gpu` failing loudly is the point: on the default, a driver hiccup or a
CPU-only torch wheel gets you a server that quietly runs 10x slower.

On Apple Silicon use `--cpu`. The engine only checks `torch.cuda`, so there's
no MPS path and the default lands on CPU anyway.

Every flag has an env equivalent: `LAYA_HOST`, `LAYA_PORT`, `LAYA_DEVICE`
(`auto`/`cpu`/`cuda`), `LAYA_MODELS`.

### As a service

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
- Laya warns on load that some checkpoints ship temperatures outside the
  calibrated range. Treat `confidence` from those buckets as uncalibrated.

## Contributing

Tests, the spec-to-client pipeline and the release process are in
[CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

Laya is by [NandhaKishorM](https://github.com/NandhaKishorM/laya) (Apache-2.0).
This repo is only the HTTP layer, and is Apache-2.0 too. See [LICENSE](LICENSE).
