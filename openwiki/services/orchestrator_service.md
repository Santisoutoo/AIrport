# Orchestrator Service

**Port 8007:8006** · [`services/orchestrator_service/`](../../services/orchestrator_service/) ·
the routing brain of AIrport. Largest service. See [architecture](../architecture.md).

## Responsibility

Receives transcribed controller transmissions, identifies the aircraft & callsign, decides which
controller (DEL/GND/TWR) owns it based on phase, forwards to the matching [agent](../agents.md),
and returns the readback. Also owns the aircraft state machine, arrival handoffs, debrief
generation, and a frequency audit.

## API — [`api/`](../../services/orchestrator_service/api/)

| Router | Path prefix | Purpose |
|---|---|---|
| [`dispatch.py`](../../services/orchestrator_service/api/dispatch.py) | `/dispatch` | **Main entry.** `POST` a `{session_id, message}`; returns `{reply, agent, aircraft_registration, callsign}`. Runs the LLM orchestrator agent |
| [`arrivals.py`](../../services/orchestrator_service/api/arrivals.py) | `/arrivals` | Arrival handoffs from the [arrival simulator](arrival_simulator_service.md) |
| [`events_subscriber.py`](../../services/orchestrator_service/api/events_subscriber.py) | — | Redis pub/sub subscriber for lifecycle events |
| [`flight_plans.py`](../../services/orchestrator_service/api/flight_plans.py) | `/flight-plans` | Flight-plan lookups |
| [`aircraft.py`](../../services/orchestrator_service/api/aircraft.py) | `/aircraft` | Aircraft records |
| [`clearances.py`](../../services/orchestrator_service/api/clearances.py) | `/clearances` | Clearance records |
| [`weather.py`](../../services/orchestrator_service/api/weather.py) | `/weather` | Weather passthrough to [weather service](weather_service.md) |
| [`debrief.py`](../../services/orchestrator_service/api/debrief.py) | `/debrief` | Post-session debrief |

Entrypoint [`main.py`](../../services/orchestrator_service/main.py); the container listens on 8006
(`/health` healthcheck). Runtime config in [`config.py`](../../services/orchestrator_service/config.py).

## Orchestrator agent — [`agent/`](../../services/orchestrator_service/agent/)

An adk/Gemini agent that routes. Definition in
[`agent/agent.py`](../../services/orchestrator_service/agent/agent.py), instruction in
[`agent/prompts.py`](../../services/orchestrator_service/agent/prompts.py); driven by
[`runner.py`](../../services/orchestrator_service/runner.py). Tools:

| Tool | Role |
|---|---|
| [`tools/aircraft.py`](../../services/orchestrator_service/agent/tools/aircraft.py) | `get_known_aircraft` — list aircraft from Postgres / flight_plan / Redis |
| [`tools/taxi_route.py`](../../services/orchestrator_service/agent/tools/taxi_route.py) | `get_taxi_route` — A\* route via [taxi_router](../shared.md) from raw instruction text |
| [`tools/advance_to_gnd.py`](../../services/orchestrator_service/agent/tools/advance_to_gnd.py) | Move aircraft DEL → GND |
| [`tools/advance_twr.py`](../../services/orchestrator_service/agent/tools/advance_twr.py) | Move aircraft GND → TWR |
| [`tools/advance_to_gnd_arrival.py`](../../services/orchestrator_service/agent/tools/advance_to_gnd_arrival.py) | Arrival handoff to GND |
| [`tools/forward.py`](../../services/orchestrator_service/agent/tools/forward.py) | Forward the transmission to the chosen DEL/GND/TWR agent, return the readback |
| [`tools/confirm.py`](../../services/orchestrator_service/agent/tools/confirm.py) | Confirmation step |

There is also a separate **debrief agent**
([`agent/debrief_agent.py`](../../services/orchestrator_service/agent/debrief_agent.py) +
`debrief_prompt.py`, assembled by
[`debrief_builder.py`](../../services/orchestrator_service/debrief_builder.py)).

## Data & support

- [`db/`](../../services/orchestrator_service/db/) — SQLAlchemy `models.py`, `repository.py`,
  `connection.py` (PostgreSQL).
- [`session_log.py`](../../services/orchestrator_service/session_log.py) — records the exact
  controller transcript per session (captured before dispatch, so a debrief survives agent errors).
- [`frequency_audit.py`](../../services/orchestrator_service/frequency_audit.py) — audits
  controller-frequency correctness.
- [`shared/callbacks.py`](../../services/orchestrator_service/shared/callbacks.py) — adk callbacks.

## Dispatch flow

`POST /dispatch` → capture transcript (`append_transcript`) → run orchestrator agent in a thread
executor → agent: get known aircraft → correct callsign → determine controller (DB dependency or
content fallback) → `forward` to DEL/GND/TWR → return `DispatchResponse`.

## Related
[architecture](../architecture.md) · [agents](../agents.md) · [shared](../shared.md) · [asr](asr_service.md) · [arrival_simulator](arrival_simulator_service.md)
