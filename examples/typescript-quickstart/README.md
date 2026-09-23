# TypeScript quickstart

The example the [README](../../README.md) points at, as a runnable folder.
`index.ts` here and the block in [`AGENTS.md`](../../AGENTS.md) are the same
file — a test fails if they drift.

You do not need this repo to use it. Copying `index.ts` into your own folder
is the whole story. This copy exists so CI can typecheck the thing the docs
tell you to paste.

```bash
docker run -d --name laya -p 127.0.0.1:11500:11500 ghcr.io/ouijan/laya-serve
until curl -sf localhost:11500/health >/dev/null; do sleep 2; done

bun install
bun run start
```

```
department   billing  (confidence 0.91)
frustration  1.55  (confidence 0.30)
churn_risk   0.8761  (confidence 0.88)

answered by english: English Latin text
178 input tokens in, 0 out
```

Edit the `state` and `questions` in `index.ts` and run it again. Every
question is answered in the same forward pass, so adding one costs nothing.

`bun run typecheck` checks it against the published client's types.
