# AGENTS.md

Read this before deciding what to change. The common request — "help me try
Laya from TypeScript" — is answered *without touching this repo*, and agents
reliably get that wrong.

## Which job is this?

**Trying it out, playing with it, prototyping, writing a demo or a test
against Laya.** You are a consumer. Do not edit this repo. The server is a
public container and the client is a public npm package. Work in a scratch
directory:

```bash
docker run -d --name laya -p 127.0.0.1:11500:11500 ghcr.io/ouijan/laya-serve
until curl -sf localhost:11500/health >/dev/null; do sleep 2; done

mkdir laya-play && cd laya-play
bun init -y
bun add @ouijan/laya-client
# then the file from README.md "Quickstart", step 3
bun run index.ts
```

Copy `index.ts` from [`examples/typescript-quickstart`](examples/typescript-quickstart)
or the README block verbatim; they are the same file, and it is typechecked
against the published client. Don't write your own from the type definitions:
hand-rolled versions hit narrowing problems this one doesn't. Adapt the
`state` and `questions` to whatever the user actually asked about, and tell
them `docker rm -f laya` stops the server.

**Changing the server, the client or the docs.** Now you are a contributor.
Read [CONTRIBUTING.md](CONTRIBUTING.md) first.

If the request is ambiguous, ask. "Set up a test to play with Laya" almost
always means the first one.

## Facts that cost people time

- **Wait for `/health`.** `docker run -d` returns in a second; the checkpoint
  takes ~30s more to become resident. A request before then fails.
- **A cold pull is ~2GB and 2-3 minutes** before that 30s even starts. Check
  `docker images | grep laya` first, and don't treat a slow pull as a hang.
- **Nothing is on your `PATH`.** `pytest` and `laya-serve` live in `.venv/bin`
  and only resolve inside a mise shell. Use `mise run test` and
  `mise run serve`, or prefix with `.venv/bin/`.
- **Do not widen `clients/typescript/tsconfig.json`'s `include`.**
  `tsconfig.build.json` extends it, so that moves the build output and breaks
  the `exports` in `package.json` — invisibly, because `dist/` is gitignored
  and it only bites on a clean CI build. Examples get their own tsconfig.
- **`clients/typescript/src/schema.ts` and `openapi.json` are generated.**
  Change `src/laya_serve/api.py`, then `cd clients/typescript && bun run build`.
- **The published client can lag this repo.** If the version in
  `pyproject.toml` isn't on npm yet, the tag hasn't shipped. Say so rather
  than pinning the example to an unpublished version. Typechecking
  `examples/typescript-quickstart` against an older published client is
  expected to fail between a schema change and its release.
- **Bumping the version needs a reinstall.** `__version__` reads installed
  metadata, so `uv pip install -e .` after editing `pyproject.toml`, before
  regenerating the spec.

## Before you report success

Run what you wrote. There is a real server available in one command and
requests take under a second, so "here's the script, start the server and try
it" is not a finished job. Show the actual output.
