# Contributing

This repository is a fork of [jakobdylanc/llmcord](https://github.com/jakobdylanc/llmcord).
That shapes how branches work here.

## Branching

**Cut a branch from `upstream/main` if the change could ever be offered upstream.**

```bash
git fetch upstream
git checkout -b fix/my-change upstream/main
```

A pull request to upstream is served from a branch in this fork, and its diff is
computed from the merge base. A branch cut from this fork's `main` carries files
upstream does not have (`.github/workflows/sync.yml`,
`.github/workflows/docker-image.yml`, `config-example.yaml`), and all of them
would show up as noise in the upstream diff.

**Cut a branch from `origin/main` for changes that are specific to this fork**,
such as the sync workflow, the Docker publishing workflow, or this file.

Do not enable "Automatically delete head branches" in repository settings. A
branch offered to upstream must keep existing while that pull request is open,
and merging the same branch into this fork's `main` would otherwise delete it.

## Tests

`pytest` runs the offline suite. It needs only pytest and pytest-asyncio; the
modules it covers are kept free of the bot's runtime dependencies.

Live tests call a real LLM provider and spend real tokens, so they carry the
`live` marker and are deselected by default. To run them, set the credentials
(a `.env` file works) and opt in:

```bash
export LLMCORD_E2E_BASE_URL=https://openrouter.ai/api/v1
export LLMCORD_E2E_API_KEY=sk-...
export LLMCORD_E2E_MODEL=openai/gpt-4o-mini
pytest -m live
```

They skip themselves when those variables are unset. Use a cheap model, and give
the key its own spend cap rather than reusing the one the bot runs on. CI does
not run them.

Model output is not deterministic, so live tests assert on properties of the
extraction prompt (durable facts survive, transient chatter does not, existing
memory is merged) rather than on exact strings.

## Commits

Conventional Commits, lowercase description, 72 characters max:

```
fix(gitignore): allow subdirectories to be committed (fixes #1)
```

Scopes in use: `gitignore`, `sync`, `ci`, `memory`, `tests`.

Add a body only when the reason for the change is not visible from the subject,
and keep it to about three lines.

## Syncing with upstream

`.github/workflows/sync.yml` runs daily at 08:00 UTC. It merges `upstream/main`
into a `sync/upstream` branch and opens a pull request against `main`. It never
pushes to `main` directly, and it fails loudly on a merge conflict rather than
resolving it in upstream's favour. Review the sync pull request like any other.
