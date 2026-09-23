# Contributing

This is for changing laya-serve. To *use* it, you want the
[README quickstart](README.md#quickstart) — that path needs no clone.

## Setup

`mise.toml` pins Python 3.13 and `uv`, and creates `.venv` on `cd` into the
directory:

```bash
mise trust
mise install      # python 3.13 + uv, creates .venv
mise run install  # uv pip install -e '.[dev]'
```

`pytest` and `laya-serve` land in `.venv/bin`, not on your global `PATH`.
Inside a mise shell the bare names work. Outside one, either prefix them
(`.venv/bin/pytest`) or use the tasks:

| Task              | Runs               |
| ----------------- | ------------------ |
| `mise run install`| `uv pip install -e '.[dev]'` |
| `mise run test`   | `pytest`           |
| `mise run serve`  | `laya-serve --cpu` |

## Tests

```bash
mise run test
```

~0.1s, no checkpoint download and no GPU: the engine is stubbed with laya's
recorded output shapes. They cover the response envelope, the answer shape of
each question type, the laya extras, `state` as string/object/turns, routing
passthrough, and the 422/500 paths.

Three are drift guards rather than behaviour. Each exists because the
documented thing and the real thing can diverge silently:

| Guard                        | Fails when                                          |
| ---------------------------- | --------------------------------------------------- |
| `tests/test_docs.py`         | the `/docs` example stops being a valid, runnable request |
| `tests/test_docs.py`         | `clients/typescript/openapi.json` is stale against the code |
| `tests/test_quickstart.py`   | `AGENTS.md`'s onboarding `index.ts` and `examples/typescript-quickstart/index.ts` disagree |
| `tests/test_version.py`      | `pyproject.toml` and `clients/typescript/package.json` disagree |

To see real model output against a running server:

```bash
python scripts/demo.py   # or: python scripts/demo.py http://your-box:11500
```

That's a demo, not a test: it prints and asserts nothing. It reads the example
out of the live server's spec, so what `/docs` shows is what it runs.

## The TypeScript client

`clients/typescript/src/schema.ts` is generated. Never hand-edit it.

```bash
cd clients/typescript && bun run build   # spec -> types -> dist
```

`bun run spec` alone rewrites `openapi.json`; it imports the app but never
starts it, so no checkpoint is downloaded and no GPU is needed. `bun run
compile` alone rebuilds `dist/` and needs no Python. Commit both
`openapi.json` and `src/schema.ts` so consumers don't need Python.

`tsconfig.json`'s `include` is load-bearing. `tsconfig.build.json` extends it,
so widening it changes tsc's inferred `rootDir` and moves the emitted files —
`dist/index.js` becomes `dist/src/index.js`, which no longer matches the
`exports` in `package.json`. `dist/` is gitignored, so that only shows up in a
clean CI build, i.e. at publish time. Keep examples in their own tsconfig.

## The quickstart example

`examples/typescript-quickstart/` depends on the *published* client, not the
local source, because that's what a new user gets. `index.ts` is byte-for-byte
the block in `AGENTS.md`; change one and `tests/test_quickstart.py` makes you
change the other.

The split is deliberate: `README.md` is a paragraph for a human deciding
whether this is worth their time, and `AGENTS.md` is the procedure, for a
coding agent pointed at its raw URL. Detail belongs in the second one.

```bash
cd examples/typescript-quickstart
bun install && bun run typecheck
```

It resolves `@ouijan/laya-client@latest` deliberately: a breaking change in a
published client should fail the example that tells people to install it.

The cost of that is a lag around a release. If you tighten a response type,
the example is written against the *new* shape while `latest` is still the old
one, so `bun run typecheck` there fails until the tag publishes. That is why
it isn't in CI: `tests/test_quickstart.py` guards the README against the
example on every run, and the typecheck is a post-release check.

`bun install --frozen-lockfile` does not work here — the lockfile is
gitignored, for the same reason.

## Docker

```bash
docker build -t laya-serve .
```

`main` publishes `:latest` on every merge, as a manifest list covering amd64
and arm64.

## Releasing

One tag ships everything. Bump `version` in `pyproject.toml` and
`clients/typescript/package.json` to the same number, regenerate the spec (it
embeds the version, and a test enforces that), then tag:

```bash
uv pip install -e .   # __version__ comes from installed metadata, not the file
cd clients/typescript && bun run build && cd ../..
git commit -am "v0.2.0" && git tag v0.2.0 && git push --tags
```

The reinstall is not optional. `laya_serve.__version__` is
`importlib.metadata.version("laya-serve")`, so until you reinstall, the spec
embeds the old number and `tests/test_version.py` fails against a
`pyproject.toml` that already looks right.

That publishes `ghcr.io/ouijan/laya-serve:0.2.0` and
`@ouijan/laya-client@0.2.0` from the same commit, plus a copy of the client on
GitHub Packages. Tests fail if the two manifests disagree or the spec is
stale.

npm publishing uses OIDC trusted publishing, so there is no npm token in the
repo. The trusted publisher is configured on the package at npmjs.com and
pinned to this repo and `publish-client.yml`.

After the tag lands, check the onboarding path against the published
artefacts: it installs `@ouijan/laya-client` from npm and pulls
`ghcr.io/ouijan/laya-serve:latest`, so it is only correct once both are up.
