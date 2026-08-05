# ADR-002: Stay on Python/FastAPI and modernize incrementally

- Status: accepted
- Date: 2026-08-05
- Context: issue #60 (backend stack decision), raised while drafting the P0–P2 improvement backlog

## Context

While drafting the backlog the question came up of whether the backend should move to
"the best possible technology" — in practice, whether to rewrite the services in Go or
Node/TypeScript. This ADR records the answer and the evidence behind it.

The state of the backend, verified against the repo rather than from memory:

| Concern | What it actually is | Where |
|---|---|---|
| Language / runtime | Python **3.11**, pinned in five places | `pyproject.toml` (`requires-python = "~=3.11.0"`), `uv.lock` (`requires-python = "==3.11.*"`), every `Dockerfile` (`FROM python:3.11-slim`), `.github/workflows/ci.yml` (`python-version: "3.11"`), and XPPython3's bundled interpreter in the sim |
| HTTP framework | **FastAPI + uvicorn**, in all six Compose services *and* the three Cloud Run agents — no exceptions | `services/*/Dockerfile`, `agents/*/requirements.txt` |
| Pilot / orchestrator agents | **`google-adk`** (Gemini) | `agents/{del,gnd,twr}/agent/agent.py`, `services/orchestrator_service/agent/`, `runner.py` |
| ASR | **`faster-whisper`** (`WhisperModel`) with a `transformers` pipeline fallback, on CPU `torch`/`torchaudio` wheels; model baked at image build | `services/asr_service/api/transcribe_service.py`, `download_model.py`, `Dockerfile` |
| Durable state | **PostgreSQL 15** via SQLAlchemy 2.0 + `psycopg2-binary` | `docker-compose.yml`, `services/*/requirements.txt` |
| Live state + bus | **Redis 7** — and it is the boundary between the Docker backend and the host-side X-Plane plugin | `docker-compose.yml`, [`openwiki/architecture.md`](../../openwiki/architecture.md) |
| Time series | **InfluxDB 2.7** (`aircraft_state`) | `docker-compose.yml` |
| Dependency management | `uv` **only at the root** (`uv.lock`); the real runtime deps live in 10 `requirements.txt` files plus inline `pip install` lines in Dockerfiles | tracked as #62 |

Two corrections to the premise stated in #60:

- **`litellm` is not part of the running system.** The only `litellm` code in the repo is
  `transcription/` — the superseded ASR prototype that is not in `docker-compose.yml` and
  whose removal is tracked in #45. The live LLM paths go through `google-adk` and
  `google-genai`.
- **Dependency management is only partly on `uv`.** The lockfile exists, but no service
  build consumes it; that gap is exactly #62.

The decisive structural fact, which the framing in #60 does not mention: the **X-Plane
plugin runs inside XPPython3's bundled CPython interpreter** and shares real modules with the
backend — `redis`, `psycopg2-binary`, `networkx`, `xplane-airports`, and the taxi-graph code
under `plugins/GND/` which the orchestrator image copies in verbatim. Python on the sim side
is not a preference; it is imposed by the plugin host.

## Decision

**Stay on Python 3.11 + FastAPI and modernize the codebase in place. Do not rewrite.**

Rationale:

1. **The domain is the Python ML/agent ecosystem.** `google-adk`, `faster-whisper`,
   `transformers` and `torch` are Python-native. A rewrite buys nothing here and loses all
   four.
2. **The sim boundary is Python by construction.** Even a perfect Go backend would leave
   `plugins/GND/` and the shared taxi router in Python, turning today's shared import into a
   duplicated implementation or a new RPC hop.
3. **There is no measured bottleneck.** Nothing in this repo has been profiled into a
   Python-bound cost. The voice→motion latency budget is dominated by Whisper inference and
   Gemini round-trips — model- and network-bound, not runtime-bound. The services are I/O
   orchestrators.
4. **The real problems are hygiene, not language.** Fragmented dependencies, no linter, no
   type checking, duplicated code across the three agents, and blocking I/O inside async
   services. Every one of them is fixable in place, and each is already a tracked issue.

## Alternatives considered

### A. Rewrite in Go — rejected

- Loses `google-adk`, `faster-whisper` and `transformers` outright; the ASR service would
  have to become a Python sidecar anyway, so Python does not actually leave the stack.
- Splits the codebase at the sim boundary: `shared/services/taxi_router/` and the
  `networkx` A\* graph in `plugins/GND/graph.py` are imported by both the orchestrator and
  the plugin today. In Go they would need a second implementation or a service call on the
  latency-sensitive path.
- Its strengths — cheap concurrency, static binaries, low memory — answer problems this
  project does not have. Concurrency is a handful of in-flight HTTP calls per controller
  transmission.

### B. Rewrite in Node/TypeScript — rejected

- Same ML ecosystem loss. Gemini is reachable from Node, but `faster-whisper` is not, so ASR
  again stays Python and the system gains a language boundary instead of removing one.
- TypeScript is already used where it pays: the controller HMI frontend was migrated to
  TypeScript + Vite in epic #59, with its own decision recorded in
  [`services/controller_hmi_service/frontend/docs/adr-001-no-global-state-library.md`](../../services/controller_hmi_service/frontend/docs/adr-001-no-global-state-library.md).
  Extending TS to the backend would not extend that benefit, since no code is shared between
  the browser and the services.

### C. Partial rewrite of a hot path (e.g. the taxi router) — rejected for now

- Plausible on paper, but premature: no profiling has identified the A\* search as a cost.
  It is also the piece most tightly coupled to the plugin, so it is the worst candidate to
  move out of Python first. Kept as a revisit trigger, not a plan.

### D. Keep the stack and change nothing — rejected

- Accepting the stack is not the same as accepting its current state. Doing nothing leaves
  the fragmentation, the missing lint/type gates and the duplicated agent runners in place,
  which is what made the "should we rewrite?" question feel reasonable in the first place.

## Decision on the target Python version

**Stay on 3.11 for now. Move to 3.12 as a single tracked step after #62; 3.13 is not on the
table yet.**

- The version is pinned in five independent places (see the table above) and must move in
  lockstep, so the bump is cheap only once #62 gives dependencies a single source of truth.
- The plugin's interpreter is whatever **XPPython3 ships** — not under this project's
  control. The backend must not move ahead of a version XPPython3 supports, or the plugin
  and the backend stop sharing installable dependencies.
- Wheel availability must be verified per version before bumping, specifically for
  `faster-whisper`/CTranslate2, `torch`/`torchaudio` and `google-adk`.
- 3.13 is deferred: CTranslate2 and torch wheels lag, and free-threading offers nothing to a
  set of I/O-bound services.

## Consequences

**Accepted:**

- The Python runtime performance profile stays. Mitigated by the workloads being I/O-bound,
  but CPU-heavy work (the taxi graph A\*) remains on Python and should stay measurable —
  one more reason to land #55.
- Async discipline has to be enforced by tooling and review rather than by the runtime.
  `services/weather_service/core/metar_taf_fetcher.py` still calls blocking `requests.get()`
  inside a FastAPI service; that is #63.
- Team knowledge stays concentrated in one language — fine for a single-maintainer project,
  and it is the same language the plugin forces anyway.

**Gained:**

- No migration budget spent; the whole modernization effort goes into the tracked issues
  below, which produce measurable improvements (lint, types, coverage, deduplication) rather
  than feature parity.
- The sim plugin and the backend keep sharing real code instead of a wire protocol.
- The "should we rewrite?" question is closed. Reopening it requires new evidence, per the
  revisit triggers below.

## Modernization steps (already tracked as issues)

| Area | Issues |
|---|---|
| Lint & format | #48 — Add ruff (lint + format) to pyproject and CI |
| Types | #50 — Gradual mypy adoption, package by package |
| Test gates | #47 — Enable a real coverage gate in CI · #49 — Characterization tests for high-coupling hotspots without direct coverage |
| Dependencies & metadata | #62 — Consolidate dependency management and fix project metadata (`uv` groups/workspaces, correct project URLs) |
| Legacy removal | #45 — Remove legacy `transcription/` service (also the repo's only `litellm` usage) · #46 — Audit and remove unreferenced modules in `shared/` and `plugins/` |
| Deduplication | #51 — Shared generic runner for the DEL/GND/TWR agents · #52 — Unify the `advance_to_gnd` / `advance_to_gnd_arrival` / `advance_twr` tools · #53 — weather_service: unify the two METAR/TAF fetch modules · #54 — Deduplicate small repeated utilities |
| Decomposition | #55 — Break up `dispatch_taxi_plan` · #56 — Break up `run_orchestrator_agent` and `_fetch_known_aircraft` · #57 — Break up `forward_to_agent` · #58 — Refactor evaluation scripts and the remaining large functions |
| Async correctness & API shape | #63 — Replace blocking `requests` calls in async services and audit broad exception handlers (consistent async `httpx` for service-to-service calls) · #64 — Group long endpoint parameter lists into pydantic request models |
| Runtime version | Python 3.12 bump — follow-up of this ADR, sequenced after #62 |

## Revisit triggers

Reopen the rewrite question if any of these happen:

1. Profiling shows a **Python-bound** (not I/O-bound) cost on the voice→motion path that
   async, caching or a native extension cannot remove.
2. A capability the system depends on stops being available in Python — e.g. the ADK or the
   Whisper serving ecosystem moves elsewhere.
3. The X-Plane integration stops going through XPPython3, removing the hard constraint that
   currently pins the sim side to Python.
4. The workload changes from one controller position to many concurrent sessions with
   per-session CPU work, making process-level concurrency a real cost rather than a
   theoretical one.

Until then, "modernize" means the issues in the table above — not a new language.
