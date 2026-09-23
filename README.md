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

**You do not need to clone this repo.** The server is a container and the
client is on npm. This takes about a minute, needs no GPU and downloads no
checkpoint — the `english` one is baked into the image.

### 1. Start the server

```bash
docker run -d --name laya -p 127.0.0.1:11500:11500 ghcr.io/ouijan/laya-serve
until curl -sf localhost:11500/health >/dev/null; do sleep 2; done
```

`docker run -d` returns before the checkpoint is resident, so wait for
`/health` rather than firing straight into a request. From a cold start that
wait is ~2-3 minutes: the image is ~2GB and the checkpoint takes ~30s to load
once it's pulled. With the image already cached it's the 30s.

It is not hung. Watch it with `docker logs -f laya` if you'd rather see
something happen.

### 2. Scaffold a project

```bash
mkdir laya-play && cd laya-play
bun init -y
bun add @ouijan/laya-client
```

### 3. Write the demo

```bash
cat > index.ts <<'EOF'
import {
	type Answer,
	createLayaClient,
	isChoice,
	isNoul,
	isScore,
} from "@ouijan/laya-client";

const laya = createLayaClient({ baseUrl: "http://localhost:11500" });

// Edit this: the situation you want decided.
const state =
	"We were billed twice for March and nobody has replied in 3 days. If this is not fixed we will move to a competitor.";

// Edit these: every question is answered in the same forward pass.
const { answers, routing, usage } = await laya.systemOne({
	state,
	questions: {
		department: {
			type: "choice",
			instructions: "Which team should handle this?",
			criteria: {
				billing: "payments, refunds, invoices",
				technical: "bugs and integrations",
				sales: "pricing and accounts",
			},
		},
		frustration: {
			type: "score",
			instructions: "How frustrated the customer appears",
			criteria: ["Calm", "Frustrated but civil", "Very angry"],
		},
		churn_risk: {
			type: "noul",
			instructions: "The customer threatens to leave",
		},
	},
});

/** `answers` is a union discriminated on `type`; narrow it and the fields follow. */
function describe(answer: Answer): string {
	if (isChoice(answer)) return answer.choice;
	if (isScore(answer)) return answer.score.toFixed(2);
	if (isNoul(answer)) return answer.noul.toFixed(4);
	return "unknown answer type";
}

for (const [id, answer] of Object.entries(answers)) {
	const confidence = answer.confidence.toFixed(2);
	console.log(`${id.padEnd(12)} ${describe(answer)}  (confidence ${confidence})`);
}

console.log(`\nanswered by ${routing?.model}: ${routing?.reason}`);
console.log(`${usage.input_tokens} input tokens in, ${usage.output_tokens} out`);
EOF
```

### 4. Run it

```bash
bun run index.ts
```

```
department   billing  (confidence 0.91)
frustration  1.55  (confidence 0.30)
churn_risk   0.8761  (confidence 0.88)

answered by english: English Latin text
178 input tokens in, 0 out
```

Requests take well under a second on CPU once the checkpoint is resident.

### 5. Change it

The questions are the interesting part. Edit `state` and `questions`, then run
it again. Adding a fourth question costs nothing: they are all answered in the
same forward pass, and `usage.output_tokens` stays at zero because nothing is
generated.

Done with it:

```bash
docker rm -f laya
```

The same example lives at
[`examples/typescript-quickstart`](examples/typescript-quickstart) if you'd
rather clone than paste. Interactive docs are at
`http://localhost:11500/docs`, where the pre-filled example is a real payload:
"Try it out" works without editing it.

### Or have an agent do it

Paste this into Claude Code, Codex, OpenCode or whatever you use. It's worded
to head off the two things agents get wrong here: cloning this repo to work
inside it, and handing back a script they never ran.

```text
Set up a TypeScript sandbox so I can play with Laya, a System One decision
engine. Work in a new folder in my current directory.

Do NOT clone github.com/ouijan/laya-serve. The server is a public container
and the client is a public npm package; you need neither the source nor a GPU.

1. Start the server:
   docker run -d --name laya -p 127.0.0.1:11500:11500 ghcr.io/ouijan/laya-serve
   `docker run -d` returns before the model is loaded, so wait for readiness
   before any request. Allow 2-3 minutes on a cold pull, ~30s if the image is
   already local. It is not hung:
   until curl -sf localhost:11500/health >/dev/null; do sleep 2; done

2. mkdir laya-play && cd laya-play && bun init -y && bun add @ouijan/laya-client

3. Write index.ts. Start from the example at
   https://github.com/ouijan/laya-serve#3-write-the-demo and copy it as-is;
   it is typechecked against the published client, so don't write your own
   from the type definitions. Then ask me what decision I want to make and
   adapt the `state` and `questions` to it. If I don't answer, leave the
   support triage example alone.

4. Run it with `bun run index.ts` and show me the real output. Don't finish by
   telling me to start the server and try it myself.

5. Tell me which lines to edit to ask it different questions, and remind me
   that `docker rm -f laya` stops the server when I'm done.
```

### Without TypeScript

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
