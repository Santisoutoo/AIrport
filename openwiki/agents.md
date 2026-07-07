# ATC Agents (DEL / GND / TWR)

The three stateless ATC pilot agents that draft ICAO-compliant readbacks. Source under
[`agents/`](../agents/). Called by the [orchestrator](services/orchestrator_service.md); see the
[architecture](architecture.md) pipeline.

## Overview

| Agent | Dir | Role |
|---|---|---|
| **DEL** — Clearance Delivery | [`agents/del/`](../agents/del/) | Issues IFR clearances (pre-pushback) |
| **GND** — Ground Control | [`agents/gnd/`](../agents/gnd/) | Pushback approval, taxi routes |
| **TWR** — Tower | [`agents/twr/`](../agents/twr/) | Takeoff / landing clearances, runway sequencing |

- **Framework:** `google-adk` (Agent Development Kit) + **Gemini** (`gemini-3-flash-preview` by
  default; via `AGENT_MODEL` / Vertex AI).
- **Deployment:** each agent is deployed **independently to Google Cloud Run** and reached by the
  orchestrator through `DEL_AGENT_URL` / `GND_AGENT_URL` / `TWR_AGENT_URL`. They are **not** part
  of `docker-compose.yml`.
- **Stateless:** the orchestrator passes all needed context (flight plan, clearances, weather,
  aircraft state) on every call; agents hold no cross-request memory of their own.

## Per-agent layout

Each agent directory follows the same shape:

```
agents/<phase>/
  main.py                     # FastAPI/HTTP entrypoint exposed on Cloud Run
  runner.py                   # google-adk Runner wiring: builds Content, runs the agent, extracts reply
  agent/agent.py              # the adk Agent definition (model, tools, instruction)
  agent/prompts/              # system / instruction prompts (ICAO phraseology rules)
  agent/tools/                # (gnd, twr) agent-side tools
  shared/callbacks.py         # (gnd, twr) adk callbacks (logging / guardrails)
  Dockerfile, requirements.txt
```

## Runner pattern

Runners use an in-memory adk session keyed by `session_id`, create the session on first contact,
then stream events and collect the final response text. Example
([`agents/gnd/runner.py`](../agents/gnd/runner.py)):

```python
_runner = Runner(agent=gnd_agent, app_name="airport_gnd", session_service=InMemorySessionService())

def run_agent(session_id, message, clearance_data=None):
    # orchestrator-provided context is appended under a [CONTEXT] block
    enriched = message + f"\n[CONTEXT]\nClearance data: {clearance_data}"
    # ... create/get session, run_async, collect event.is_final_response() text
```

The orchestrator enriches each call with pre-fetched context so the agent doesn't have to fetch
data itself. GND, for instance, receives `clearance_data`.

## How the orchestrator reaches them

The orchestrator's `forward` tool
([`services/orchestrator_service/agent/tools/forward.py`](../services/orchestrator_service/agent/tools/forward.py))
posts the transmission to the selected agent's endpoint and returns the readback. Which agent is
chosen depends on the aircraft's phase (see the state machine in [architecture](architecture.md)).

## Evaluation

Agent quality and WER are benchmarked against phase-specific corpora under
[`agents_evaluation/`](../agents_evaluation/) (`corpus_wer/del|gnd|twr`). See
[data-and-testing](data-and-testing.md).

## Related
[index](index.md) · [architecture](architecture.md) · [orchestrator](services/orchestrator_service.md) · [data-and-testing](data-and-testing.md)
