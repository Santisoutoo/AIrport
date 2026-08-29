# System Overview

Every module of AIrport, what it does, and how they relate. This is the human-facing map;
the agent-facing deep dive is [Architecture](../architecture.md).

## Voice → motion pipeline

![Architecture](https://raw.githubusercontent.com/Santisoutoo/AIrport/main/docs/diagrams/images/architecture.svg)

1. The controller speaks an instruction into the mic in the Controller HMI.
2. The **ASR service** transcribes it with an ATC-fine-tuned Whisper model and corrects the
   callsign, then forwards the text to the Orchestrator's `/dispatch`.
3. The **Orchestrator** decides which aircraft the message is for and which phase it is in
   (`DEL → GND → TWR`), prefetches context (flight plan, ATIS, clearance, taxi route), and
   calls the matching **pilot agent** on Cloud Run.
4. The agent (Gemini) drafts an ICAO-compliant pilot readback; for a taxi acknowledgement the
   Orchestrator also computes the taxi plan with the shared A\* **taxi router** and publishes
   movement commands to **Redis**.
5. The **X-Plane plugin** consumes the movement plan, moves/spawns the aircraft in the
   simulator, and speaks the readback with X-Plane's built-in TTS.

Diagram sources live in [`docs/diagrams/`](../../docs/diagrams/).

## Modules

| Module | Responsibility | Talks to | Key config |
|---|---|---|---|
| [Controller HMI](../services/controller_hmi_service.md) `:8005` | Web UI (flight strips, ground radar, chat) + API gateway | proxies ASR, Orchestrator, Flight Plan, Weather; Redis state + `hmi:chat` | `ASR_URL`, `ORCHESTRATOR_URL`, `DB_*` |
| [ASR](../services/asr_service.md) `:8006` | Whisper ATC transcription + callsign correction | → Orchestrator `/dispatch` | `ASR_*`, `ASR_LLM_MODEL`, Vertex vars |
| [Orchestrator](../services/orchestrator_service.md) `:8007` | Routing, `DEL→GND→TWR` state machine, dispatch, debrief | → agents, Flight Plan, Weather, Postgres, Redis | `DEL/GND/TWR_AGENT_URL`, `AGENT_MODEL` |
| [Flight Plan](../services/flight_plan_service.md) `:8003` | IFR flight plan generation (flightplandatabase.com + local fallback) | ← HMI, Orchestrator, Arrival Simulator; Postgres | `FLIGHT_PLAN_GENERATOR_KEY` |
| [Weather](../services/weather_service.md) `:8004` | METAR/TAF fetch (aviationweather.gov), ATIS generation | ← HMI, Orchestrator; Postgres | — |
| [Arrival Simulator](../services/arrival_simulator_service.md) `:8008` | Spawns AI arrivals on the ILS, drives approach → vacate | → Flight Plan, HMI, Orchestrator, Redis | `ARRIVAL_*` |
| [Pilot agents](../agents.md) (Cloud Run) | DEL/GND/TWR Gemini pilots: interpret instruction, draft readback | ← Orchestrator (`POST /agents/<role>/run`) | `AGENT_MODEL`, Vertex identity |
| [Shared package](../shared.md) | Models, A\* taxi router, aircraft state store, stand assigner, geo helpers | imported by Orchestrator, Arrival Simulator, plugin | — |
| [X-Plane side](../xplane.md) | In-sim plugin: spawner, mover, TTS readback | ← Redis movement plan; → Orchestrator `:8007` | see [X-Plane Plugin Setup](xplane-plugin-setup.md) |
| PostgreSQL `:5432` | Flight plans, ATIS history, clearances | ← services | `POSTGRES_*` |
| Redis `:6379` | Aircraft state, movement commands, `hmi:chat`, `tts:queue` | ← services + plugin | `REDIS_*` |
| InfluxDB `:8087` | Metrics/time series | ← services | `INFLUXDB_ORG`, `INFLUXDB_BUCKET` |

Ports are host-side, from [`docker-compose.yml`](../../docker-compose.yml). Every app service
listens on `8000` inside its container except the Orchestrator, which listens on `8006`
(exposed as host `8007`) — details in [Configuration](configuration.md).

## How modules talk

- **HTTP** — the HMI is the gateway for the browser; ASR → Orchestrator → agents is the
  dispatch chain; Orchestrator, HMI and Arrival Simulator call Flight Plan and Weather.
- **Redis** — aircraft live state (`aircraft:active_set`, `aircraft:state:{reg}`), movement
  command plans consumed by the X-Plane plugin, `hmi:chat` pub/sub fanned out to the browser
  via the HMI WebSocket, `tts:queue` for spoken readbacks, and `aircraft:*:move_events`
  which the Orchestrator records for the session debrief.
- **PostgreSQL** — flight plans (Flight Plan), ATIS history (Weather), clearances (Orchestrator).

## Legacy & placeholder directories

Not part of the active pipeline — don't be confused by them:

- [`services/pilots_communication/`](../../services/pilots_communication/) — early prototype of
  what ASR + Orchestrator now do together.
- `services/analytics_service`, `nlp_service`, `tts_service`, `xplane_manager` — empty
  placeholders (TTS today is X-Plane's built-in speech).

## Related

[Installation](installation.md) · [Quickstart](quickstart.md) · [Configuration](configuration.md) · [Architecture](../architecture.md)
