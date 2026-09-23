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

Start from this. Don't write your own from the type definitions: `answers` is
a union keyed by your question ids, and hand-rolled versions get the narrowing
wrong.

```ts
import { createLayaClient, isChoice, isNoul, isScore } from "@ouijan/laya-client";

const laya = createLayaClient({ baseUrl: "http://localhost:11500" });

// Every question is answered in the same forward pass, so a fourth is free.
const { answers, routing, usage } = await laya.systemOne({
  state:
    "We were billed twice for March and nobody has replied in 3 days. " +
    "If this is not fixed we will move to a competitor.",
  questions: {
    department: {
      type: "choice",
      instructions: "Which team should handle this?",
      criteria: { billing: "payments and refunds", technical: "bugs" },
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

const { department, frustration, churn_risk } = answers;

if (isChoice(department)) console.log(department.choice, department.confidence);
if (isScore(frustration)) console.log(frustration.score.toFixed(2));
if (isNoul(churn_risk)) console.log(churn_risk.noul, churn_risk.confidence);

console.log(routing?.model, routing?.reason);
console.log(usage.input_tokens, "input tokens,", usage.output_tokens, "output");
```

Narrow every answer with `isChoice`, `isScore` or `isNoul` before reading its
fields; the type discriminator is what makes the rest of them available.

Then ask the user what decision they actually want to make, and adapt `state`
and `questions` to it. If they don't answer, leave the support triage example
as it is.

### 4. Run it and show the output

```bash
bun run index.ts
```

```
billing 0.6841
1.55
0.8761 0.8761
english English Latin text
166 input tokens, 0 output
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
  and it only bites on a clean CI build.
- **`clients/typescript/src/schema.ts` and `openapi.json` are generated.**
  Change `src/laya_serve/api.py`, then `cd clients/typescript && bun run build`.
- **Bumping the version needs a reinstall.** `__version__` reads installed
  metadata, so `uv pip install -e .` after editing `pyproject.toml`, before
  regenerating the spec.
- **The `index.ts` above is not compiled by CI.** Nothing catches it drifting
  from the client's real API, so if you change `createLayaClient` or the
  answer types, update it here and in `README.md` by hand.
- **The published client can lag this repo.** If the version in
  `pyproject.toml` isn't on npm yet, the tag hasn't shipped. Say so rather
  than documenting an API nobody can install.
