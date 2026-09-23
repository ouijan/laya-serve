# AGENTS.md

Read this before deciding what to change. The common request — "help me try
Laya from TypeScript" — is answered *without touching this repo*, and agents
reliably get that wrong.

## Which job is this?

**Trying it out, playing with it, prototyping, writing a demo or a test
against Laya.** You are a consumer. Do not edit or clone this repo. Follow
[Onboarding a new user](#onboarding-a-new-user) below.

**Changing the server, the client or the docs.** You are a contributor. Read
[CONTRIBUTING.md](CONTRIBUTING.md), then [Working on this repo](#working-on-this-repo).

If the request is ambiguous, ask. "Set up a test to play with Laya" almost
always means the first one.

## Onboarding a new user

Laya is a System One decision engine: you give it a state and typed questions,
it answers all of them in one forward pass. No text generation, so there is no
JSON to parse out of prose. Questions are `choice` (pick an option), `score`
(position on a scale you define) or `noul` (probability a statement holds).

Everything below runs in the user's own workspace. The server is a public
container and the client is a public npm package; you need neither the source
nor a GPU.

### 1. Start the server

```bash
docker run -d --name laya -p 127.0.0.1:11500:11500 ghcr.io/ouijan/laya-serve
until curl -sf localhost:11500/health >/dev/null; do sleep 2; done
```

`docker run -d` returns before the checkpoint is resident, so the wait is not
optional. Allow 2-3 minutes on a cold pull (~2GB image, then ~30s to load the
checkpoint) and ~30s if the image is already local. Check
`docker images | grep laya` first. A slow pull is not a hang — say so rather
than killing it.

### 2. Scaffold a folder

In a new directory beside whatever the user is working on, never inside this
repo:

```bash
mkdir laya-play && cd laya-play
bun init -y
bun add @ouijan/laya-client
```

### 3. Write index.ts

Copy this verbatim. It is typechecked in CI against the published client, so
it compiles. Do not write your own from the type definitions: hand-rolled
versions hit narrowing problems this one doesn't.

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

Then ask the user what decision they actually want to make, and adapt `state`
and `questions` to it. If they don't answer, leave the support triage example
as it is.

### 4. Run it and show the output

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

Run what you wrote. A server is one command away and requests take under a
second, so "here's the script, start the server and try it" is not a finished
job.

### 5. Hand over

Tell the user which lines to edit to ask different questions, that a fourth
question costs nothing because they share one forward pass, and that
`docker rm -f laya` stops the server. Leave the container running unless they
say otherwise — they'll want it for the next question.

Worth mentioning: the base checkpoints score near chance on typed decisions
zero-shot. The numbers demonstrate the shape, not the accuracy. Real use needs
fine-tuning.

## Working on this repo

Facts that cost people time:

- **Nothing is on your `PATH`.** `pytest` and `laya-serve` live in `.venv/bin`
  and only resolve inside a mise shell. Use `mise run test` and
  `mise run serve`, or prefix with `.venv/bin/`.
- **Do not widen `clients/typescript/tsconfig.json`'s `include`.**
  `tsconfig.build.json` extends it, so that moves the build output and breaks
  the `exports` in `package.json` — invisibly, because `dist/` is gitignored
  and it only bites on a clean CI build. Examples get their own tsconfig.
- **`clients/typescript/src/schema.ts` and `openapi.json` are generated.**
  Change `src/laya_serve/api.py`, then `cd clients/typescript && bun run build`.
- **Bumping the version needs a reinstall.** `__version__` reads installed
  metadata, so `uv pip install -e .` after editing `pyproject.toml`, before
  regenerating the spec.
- **The `index.ts` above is guarded.** `tests/test_quickstart.py` fails if it
  drifts from `examples/typescript-quickstart/index.ts`. Change both.
- **The published client can lag this repo.** If the version in
  `pyproject.toml` isn't on npm yet, the tag hasn't shipped. Typechecking
  `examples/typescript-quickstart` against an older published client is
  expected to fail between a schema change and its release.
