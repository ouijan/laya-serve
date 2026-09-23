# @ouijan/laya-client

Typed client for `laya-serve`. The types in `src/schema.ts` are generated
from the server's own OpenAPI spec, so they cannot drift from the API.

Names mirror the [TypeSafe SDK](https://docs.typesafe.ai/sdk) — `systemOne`,
`ChoiceAnswer`, `ScoreAnswer`, `NoulAnswer` — so swapping between this server
and the hosted Jev API is a change of import, not of code.

## Install

Published to the public npm registry:

```bash
npm add @ouijan/laya-client   # or bun add / pnpm add
```

Also published to GitHub Packages. That registry needs a token even for
public packages, so only use it if you specifically want it:

```ini
# .npmrc
@ouijan:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${GITHUB_TOKEN}
```

The package ships compiled JS and `.d.ts`, so it works under Node, bundlers
and bun alike. Inside this repo, depend on it by path instead:

```bash
bun add file:../laya-serve/clients/typescript
```

## Use

```ts
import { createLayaClient, isChoice, isScore, isNoul } from "@ouijan/laya-client";

const laya = createLayaClient({ baseUrl: "http://your-box:11500" });

const { answers, usage, routing } = await laya.systemOne({
  state: "We were billed twice for March. We'll move to a competitor.",
  questions: {
    department: {
      type: "choice",
      instructions: "Which team should handle this?",
      criteria: { billing: "invoices, refunds", technical: "bugs", sales: "pricing" },
    },
    frustration: {
      type: "score",
      instructions: "How frustrated the customer appears",
      criteria: ["Calm", "Frustrated but civil", "Very angry"],
    },
    churn_risk: { type: "noul", instructions: "The customer threatens to leave" },
  },
});
```

`answers` is a discriminated union on `type`. Narrow it and the rest of the
fields follow:

```ts
for (const [id, answer] of Object.entries(answers)) {
  if (isChoice(answer)) console.log(id, answer.choice, answer.probabilities);
  else if (isScore(answer)) console.log(id, answer.score, answer.legend);
  else if (isNoul(answer)) console.log(id, answer.noul);
}
```

`state` accepts a string, an object or a list of conversation turns.

### laya extras

Beyond Jev's fields you also get `routing` (which of the three checkpoints
answered, and why) and `action.act_probability` on each answer. `noul` answers
carry a `confidence` that the hosted API does not return.

```ts
routing?.model;   // "multilingual"
routing?.reason;  // "non-Latin script (cyrillic, 100% of letters); ..."
```

`laya.route(...)` returns just that decision, with no forward pass.

### Errors

Non-2xx responses throw `LayaError`, carrying `status` and `detail`.

Pass `fetch` to supply your own implementation, e.g. for timeouts:

```ts
createLayaClient({
  baseUrl,
  fetch: (req) => fetch(req, { signal: AbortSignal.timeout(10_000) }),
});
```

## Versioning

The client version tracks the server's, and a single `v<semver>` tag ships
both. `@ouijan/laya-client@0.1.0` is built from the same commit as
`ghcr.io/ouijan/laya-serve:0.1.0`, so pin them to the same number. A test
fails if `package.json` and `pyproject.toml` disagree.

```bash
# bump both, then:
git tag v0.2.0 && git push --tags
```

## Regenerating after an API change

```bash
bun run build   # spec -> types -> dist
```

`bun run spec` alone rewrites `openapi.json` and needs the Python package;
`bun run compile` alone rebuilds `dist/` and does not.

`bun run spec` alone rewrites `openapi.json`; it imports the app but never
starts it, so no checkpoint is downloaded and no GPU is needed. Commit both
`openapi.json` and `src/schema.ts` so consumers don't need Python.
