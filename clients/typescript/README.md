# @ouijan/laya-client

Typed client for `laya-serve`. The types in `src/schema.d.ts` are generated
from the server's own OpenAPI spec, so they cannot drift from the API.

## Use

```ts
import { createLayaClient, LayaError } from "@ouijan/laya-client";

const laya = createLayaClient({ baseUrl: "http://your-box:11500" });

const { answers, routing } = await laya.predict({
  state: { subject: "Duplicate charge", body: "We were billed twice for March." },
  questions: {
    department: {
      type: "choice",
      instructions: "Which department should handle this?",
      criteria: { billing: "invoices, refunds", technical: "bugs" },
    },
  },
});

console.log(routing?.model, answers.department);
```

`answers` is `Record<string, unknown>` by design — its shape depends on the
questions you send, so the server cannot describe it up front. Narrow it
yourself at the call site. Everything else (`routing`, `/health`, the request
body) is fully typed.

Non-2xx responses throw `LayaError`, which carries `status` and `detail`.

Pass `fetch` to supply your own implementation, e.g. for timeouts:

```ts
createLayaClient({
  baseUrl,
  fetch: (req) => fetch(req, { signal: AbortSignal.timeout(10_000) }),
});
```

## Regenerating after an API change

```bash
bun run build   # dumps openapi.json from the Python package, then regenerates
```

`bun run spec` alone rewrites `openapi.json`; it imports the app but never
starts it, so no checkpoint is downloaded and no GPU is needed. Commit both
`openapi.json` and `src/schema.d.ts` so consumers don't need Python.
