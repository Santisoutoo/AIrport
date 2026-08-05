# Contributing

Thank you for your interest in contributing to this project!

## Pull Requests

> **Pull Requests are not being accepted until the end of June 2026.**

The project is currently in an early development phase. Please hold off on
submitting PRs for now -- contributions will be welcome once this restriction
is lifted.

In the meantime, feel free to:
- Open issues to report bugs or suggest features
- Fork the project for personal experimentation

We appreciate your patience and support.

## Development setup

The project is managed with [uv](https://github.com/astral-sh/uv) and a single
lockfile at the repo root.

```bash
uv sync                  # runtime deps only
uv sync --extra test     # + the pytest stack
uv sync --extra analysis # + notebooks, plots and ASR benchmarking
uv run pytest
```

## Dependency layout

The root `pyproject.toml` is the **single source of truth** for Python
dependencies:

- `[project].dependencies` — what the backend needs to run and be tested.
  Research/notebook packages are deliberately **not** here.
- `[project.optional-dependencies]` — one extra per deployable unit
  (`orchestrator`, `agents`, `asr`, `weather`, …) plus `service-core` (the
  FastAPI stack shared by every service image), `analysis` (notebooks, plots,
  WER benchmarking) and `test`.

The per-service `requirements.txt` files that the Dockerfiles install are
**generated** from those extras — they carry a `GENERATED FILE -- DO NOT EDIT`
header. To change a service's dependencies, edit the matching extra and
regenerate:

```bash
python scripts/sync_requirements.py
```

CI runs `python scripts/sync_requirements.py --check` and fails if a generated
file drifts from `pyproject.toml`. The mapping of service directory to extras
lives in `SERVICES` at the top of that script.
