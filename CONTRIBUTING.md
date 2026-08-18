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

They also work as a fitness check on a candidate `memory_model`. A small model
that summarises the exchange instead of declining to record anything will fail
`test_extraction_ignores_transient_chatter`, which is a verdict on the model
rather than a broken test. Point the variables at a local server to run them
for free, for example llama.cpp on `http://localhost:8080/v1`.

## Dependencies

`requirements.txt` and `requirements-dev.txt` declare what the project needs.
`requirements.lock` and `requirements-dev.lock` pin every resolved version,
including transitive ones, with hashes. The Docker image and CI install from
the locks with `--only-binary :all: --require-hashes`, so an install can
neither run a setup script nor pick up a version nobody reviewed.

Regenerate both after changing either declaration file:

```bash
uv pip compile --generate-hashes --python-version 3.13 --only-binary :all: \
  requirements.txt -o requirements.lock
uv pip compile --generate-hashes --python-version 3.13 --only-binary :all: \
  requirements.txt requirements-dev.txt -o requirements-dev.lock
```

`requirements-dev.lock` covers the runtime dependencies too, which is why CI
installs it alone.

`requirements.txt` belongs to upstream, so a sync can change it without
touching the locks. CI installs from the lock and the tests import the runtime
modules, so a dependency added upstream fails the sync pull request rather than
slipping through. Regenerate the locks in that pull request.

## Commits

Conventional Commits, lowercase description, 72 characters max:

```
fix(gitignore): allow subdirectories to be committed (fixes #1)
```

Scopes in use: `gitignore`, `sync`, `ci`, `memory`, `tests`.

Add a body only when the reason for the change is not visible from the subject,
and keep it to about three lines.

`.githooks/commit-msg` enforces that. Git does not enable a checked-in hook by
itself, so point the clone at the directory once:

```bash
git config core.hooksPath .githooks
```

The hook rejects a subject that misses the `type(scope): description` shape,
starts the description with a capital, ends it with a period, or runs past 72
characters. It leaves merge, revert, and fixup subjects alone.

Two more checks run the same script, so the rules are stated once:

- `.github/workflows/commits.yml` checks every non-merge commit in a pull
  request. This is the check that cannot be skipped with `--no-verify`.
- `.claude/settings.json` registers `.githooks/claude-commit-msg` as a Claude
  Code `PreToolUse` hook. It reads the message out of a `git commit` command
  and refuses the command before git runs, so a bad subject is rewritten rather
  than committed and amended.

## Syncing with upstream

`.github/workflows/sync.yml` runs daily at 08:00 UTC. It merges `upstream/main`
into a `sync/upstream` branch and opens a pull request against `main`. It never
pushes to `main` directly, and it fails loudly on a merge conflict rather than
resolving it in upstream's favour. Review the sync pull request like any other.
