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

## Getting started

The image has the `english` checkpoint baked in, so this needs no volume, no
model download and no GPU:

```bash
docker run -d -p 127.0.0.1:11500:11500 ghcr.io/ouijan/laya-serve
```

Ask it something:

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

Interactive docs are at `http://localhost:11500/docs`, and the example there
is a real payload: "Try it out" works without editing it.

From TypeScript:

```bash
npm add @ouijan/laya-client
```

```ts
import { createLayaClient, isChoice } from "@ouijan/laya-client";

const laya = createLayaClient({ baseUrl: "http://localhost:11500" });
const { answers } = await laya.systemOne({ state, questions });

if (isChoice(answers.department)) {
  console.log(answers.department.choice); // "billing"
}
```

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

[`clients/typescript`](clients/typescript) is generated from this server's
OpenAPI spec, so the types can't drift from the API. Names mirror the TypeSafe
SDK, so moving between this and the hosted API is a change of import.

```ts
const { answers, routing, usage } = await laya.systemOne({
  state: "We were billed twice for March. We'll move to a competitor.",
  questions: {
    department: {
      type: "choice",
      instructions: "Which team should handle this?",
      criteria: { billing: "invoices, refunds", technical: "bugs" },
    },
    churn_risk: { type: "noul", instructions: "The customer threatens to leave" },
  },
});
```

`answers` is a discriminated union on `type`: narrow with `isChoice`,
`isScore` or `isNoul` and the remaining fields follow.

Regenerate after changing an endpoint:

```bash
cd clients/typescript && bun run build
```

## Docker

Published from `main` as a manifest list covering amd64 and arm64, so a pull
resolves to the right architecture. Build it yourself with:

```bash
docker build -t laya-serve .
```

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

## Running on the host

Needs Python 3.10–3.13 (torch has no 3.14 wheels yet). `mise.toml` pins the
interpreter and `uv`, and creates `.venv` on `cd` into the directory:

```bash
mise trust
mise install      # python 3.13 + uv, creates .venv
mise run install  # uv pip install -e '.[dev]'
laya-serve --cpu
```

Without mise, any venv on Python ≤3.13 works. A Homebrew Python refuses a
system-wide install (PEP 668), so the venv isn't optional:

```bash
uv venv --python 3.13 && uv pip install -e .
```

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

## Releasing

One tag ships everything. Bump `version` in `pyproject.toml` and
`clients/typescript/package.json` to the same number, regenerate the spec
(it embeds the version, and a test enforces that), then tag:

```bash
cd clients/typescript && bun run build && cd ../..
git commit -am "v0.2.0" && git tag v0.2.0 && git push --tags
```

That publishes `ghcr.io/ouijan/laya-serve:0.2.0` and
`@ouijan/laya-client@0.2.0` from the same commit, plus a copy of the client
on GitHub Packages. `main` also publishes `:latest` on every merge. Tests fail
if the two manifests disagree or the spec is stale.

npm publishing uses OIDC trusted publishing, so there is no npm token in the
repo. The trusted publisher is configured on the package at npmjs.com and
pinned to this repo and `publish-client.yml`.

## Development

```bash
mise run test   # or: pytest
```

22 tests, ~0.1s, no checkpoint download and no GPU: the engine is stubbed with
laya's recorded output shapes. They cover the response envelope, the answer
shape of each question type, the laya extras, `state` as string/object/turns,
routing passthrough, and the 422/500 paths.

Two are drift guards rather than behaviour:

- the `/docs` example must be a valid request, and must actually run
- `clients/typescript/openapi.json` must match the code, so the TypeScript
  client can't be generated from a stale spec

To see real model output against a running server:

```bash
python scripts/demo.py   # or: python scripts/demo.py http://your-box:11500
```

That's a demo, not a test: it prints and asserts nothing. It reads the example
out of the live server's spec, so what `/docs` shows is what it runs.

## Caveats

- No auth, no TLS. Localhost or behind a reverse proxy.
- Single process, no batching queue. Concurrent requests serialise on the GPU.
  Fine for low-hundreds of req/min; put a queue in front if you need more.
- Base checkpoints score near chance on typed decisions zero-shot. Fine-tune
  before trusting the numbers.
- Laya warns on load that some checkpoints ship temperatures outside the
  calibrated range. Treat `confidence` from those buckets as uncalibrated.

## Credits

Laya is by [NandhaKishorM](https://github.com/NandhaKishorM/laya) (Apache-2.0).
This repo is only the HTTP layer, and is Apache-2.0 too. See [LICENSE](LICENSE).
