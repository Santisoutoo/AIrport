# Architecture

End-to-end design of AIrport: how a spoken controller instruction becomes aircraft motion in
X-Plane 12. See [index](index.md) for the page map.

## Voice → motion pipeline

1. **Controller speaks** into the mic in the Controller HMI web UI
   ([controller_hmi_service](services/controller_hmi_service.md), port 8005).
2. **ASR** ([asr_service](services/asr_service.md), 8006) transcribes the audio with a Whisper
   model fine-tuned for ATC, then corrects the callsign (phonetics + LLM corrector).
3. **Orchestrator** ([orchestrator_service](services/orchestrator_service.md), 8007) receives the
   transcript at `POST /dispatch`. An LLM orchestrator agent (google-adk + Gemini):
   - looks up known aircraft (PostgreSQL / flight-plan service / Redis),
   - identifies & corrects the callsign,
   - decides the responsible controller from the aircraft's **phase** (`DEL → GND → TWR`),
   - forwards the message to the matching agent and returns the reply.
4. **ATC agent** ([agents](agents.md), DEL/GND/TWR on Cloud Run) drafts the ICAO-compliant pilot
   readback with Gemini, using context (flight plan, clearances, weather) supplied by the orchestrator.
5. **Taxi routing** ([shared/services/taxi_router](shared.md)) computes an A\* taxi route with
   pushback leg and dispatches a multi-leg move plan (via Redis) to the plugin.
6. **X-Plane plugin** ([xplane](xplane.md)) moves/spawns the aircraft and speaks the readback with
   X-Plane's built-in TTS.

```
Controller mic
   │ audio
   ▼
ASR (Whisper-ATC + callsign correction)          services/asr_service  :8006
   │ transcript
   ▼
Orchestrator  POST /dispatch                      services/orchestrator_service :8007
   │  • identify aircraft + callsign (Postgres / Redis / flight_plan)
   │  • pick controller by phase (DEL→GND→TWR)
   │  • agent tools: get_taxi_route, advance_to_gnd, advance_twr, forward, confirm
   ▼ forward
DEL / GND / TWR agent (Gemini, google-adk)        agents/  → Cloud Run (*_AGENT_URL)
   │ ICAO readback
   ▼
taxi_router (A* route + pushback) ── Redis move plan ──▶ X-Plane plugin  (xplane_plugin/, plugins/)
                                                                │
                                                                ▼
                                                    aircraft moves + TTS readback
```

## Aircraft phase state machine

The orchestrator tracks each aircraft through phases defined in
[`shared/models/phases.py`](../shared/models/phases.py). Phase determines which controller owns
the aircraft and which agent gets the message:

- **Departure:** `parked → pushback → taxi_out → holding → lineup → takeoff_roll → airborne`
- **Arrival:** `approach → short_final → landing_roll → vacating → taxi_in`

Controller mapping: **DEL** (clearance, pre-pushback) → **GND** (pushback, taxi) → **TWR**
(lineup, takeoff/landing). Orchestrator agent tools `advance_to_gnd`, `advance_twr`, and
`advance_to_gnd_arrival` move an aircraft between controllers.

## Service topology

All application services are FastAPI + Uvicorn, containerized via
[`docker-compose.yml`](../docker-compose.yml). Ports are `host:container`.

| Service | Port | Talks to |
|---|---|---|
| [Controller HMI](services/controller_hmi_service.md) | 8005:8000 | asr, orchestrator, flight_plan, weather, Postgres, Redis |
| [Flight Plan](services/flight_plan_service.md) | 8003:8000 | Postgres, flightplandatabase.com |
| [Weather](services/weather_service.md) | 8004:8000 | Postgres, external METAR/TAF sources |
| [ASR](services/asr_service.md) | 8006:8000 | Redis, orchestrator |
| [Orchestrator](services/orchestrator_service.md) | 8007:8006 | flight_plan, weather, Postgres, Redis, DEL/GND/TWR agents |
| [Arrival Simulator](services/arrival_simulator_service.md) | 8008:8000 | Redis, flight_plan, orchestrator, HMI |

The three ATC agents are **not** in Compose — they deploy independently to **Google Cloud Run**
and are reached through `DEL_AGENT_URL` / `GND_AGENT_URL` / `TWR_AGENT_URL`.

## Data stores

| Store | Image | Port | Used for |
|---|---|---|---|
| PostgreSQL | `postgres:15-alpine` | 5432:5432 | Flight plans, clearances, aircraft records, weather/ATIS (`config/postgres/init.sql`) |
| Redis | `redis:7-alpine` | 6379:6379 | Aircraft state store, live positions, move-command plans, pub/sub events |
| InfluxDB | `influxdb:2.7-alpine` | 8087:8086 | Time-series (telemetry/metrics) |

## Inter-service communication

- **HTTP (REST):** services call each other via the `*_SERVICE_URL` / `*_AGENT_URL` env vars
  (see the `environment:` blocks in [`docker-compose.yml`](../docker-compose.yml)). Each service
  exposes a `/health` endpoint used by Compose healthchecks.
- **Redis pub/sub:** the orchestrator subscribes to events via
  [`api/events_subscriber.py`](../services/orchestrator_service/api/events_subscriber.py); the
  arrival simulator publishes arrival lifecycle events (`core/event_bridge.py`). Aircraft state
  and move plans flow through Redis keys consumed by the plugin.

## Two main flows

- **Departure pipeline:** HMI → ASR → orchestrator `/dispatch` → DEL→GND→TWR → taxi_router → plugin.
  Integration test: [`tests/integration/test_departure_pipeline.py`](../tests/integration/test_departure_pipeline.py).
- **Arrival pipeline:** [arrival_simulator](services/arrival_simulator_service.md) spawns aircraft
  on the ILS and drives them through arrival phases to vacate/taxi-in; orchestrator handles arrival
  handoffs (`api/arrivals.py`, `advance_to_gnd_arrival`).
  Integration test: [`tests/integration/test_arrival_pipeline.py`](../tests/integration/test_arrival_pipeline.py).

## Related
[index](index.md) · [agents](agents.md) · [orchestrator](services/orchestrator_service.md) · [shared](shared.md) · [xplane](xplane.md)
