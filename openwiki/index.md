# AIrport — agent-facing documentation (openwiki)

> This is **not** human prose documentation (that lives under [`docs/`](../docs)). This is a
> structured reference for an LLM/coding-agent working in this repo: short sections, tables,
> and cross-links. Start here, then follow the links below to the page you need.

## What is AIrport

AIrport is an AI-powered Air Traffic Control (ATC) training simulator built on **X-Plane 12**.
A human plays the controller: they speak an ATC instruction into a mic, the system transcribes
it with an ATC-fine-tuned Whisper model, an LLM **orchestrator** figures out which aircraft and
which controller phase (Delivery / Ground / Tower) the message belongs to, a **Gemini agent**
(via `google-adk`, running on Cloud Run) drafts the ICAO-compliant pilot readback, and the
**X-Plane plugin** actually moves/spawns the aircraft in the simulator and speaks the readback
back with X-Plane's built-in TTS. Backend: Python 3.11, `uv`-managed, FastAPI microservices,
Docker Compose. See [`README.md`](../README.md) for the human-facing project overview.

## Architecture at a glance

```
Controller mic ──▶ ASR (Whisper ATC) ──▶ Orchestrator (LLM router) ──▶ DEL/GND/TWR agent (Gemini)
                                              │  DB: aircraft phase (DEL→GND→TWR)         │
                                              ▼                                            ▼
                                     shared/services/taxi_router               ICAO pilot readback
                                              │                                            │
                                              ▼                                            ▼
                                     Redis move_cmd plan ───────────▶ X-Plane plugin (mover/spawner)
                                                                              │
                                                                              ▼
                                                                    aircraft moves + speaks (TTS)
```

Full breakdown, ports, and data stores: [architecture.md](architecture.md).

## Pages

| Page | Covers |
|---|---|
| [architecture.md](architecture.md) | End-to-end voice→motion pipeline, microservice topology, data stores, inter-service communication (HTTP + Redis pub/sub) |
| [agents.md](agents.md) | The DEL / GND / TWR Gemini pilot agents: prompts, runner, callbacks, Cloud Run deployment shape |
| [services/orchestrator_service.md](services/orchestrator_service.md) | Agent routing, aircraft phase state machine, dispatch, debrief generation, frequency audit |
| [services/asr_service.md](services/asr_service.md) | Whisper transcription + callsign correction, dispatch to the orchestrator |
| [services/weather_service.md](services/weather_service.md) | METAR/TAF fetch, ATIS generation |
| [services/flight_plan_service.md](services/flight_plan_service.md) | IFR flight plan generation (API-backed + local fallback) |
| [services/arrival_simulator_service.md](services/arrival_simulator_service.md) | Spawns AI arrivals on the ILS, drives them to vacate, maintains a minimum concurrent count |
| [services/controller_hmi_service.md](services/controller_hmi_service.md) | Web UI (flight strips, ground radar, ATIS/chat) and API gateway to the other services |
| [shared.md](shared.md) | Cross-service `shared/` package: models, taxi router (A\* graph routing), aircraft state store, stand assigner, geo helpers |
| [xplane.md](xplane.md) | `xplane_plugin/` (in-sim XPPython3 plugin) and `plugins/` (deployable X-Plane files): spawner, mover, airport graph parsing |
| [data-and-testing.md](data-and-testing.md) | `data/` (LEBL airport data, scripts, notebooks), `agents_evaluation/` (WER + agent benchmarks), `tests/` layout |

## Services (active, wired into `docker-compose.yml`)

| Service | Host port | Responsibility |
|---|---|---|
| Controller HMI | 8005 | Web UI (flight strips, ground radar, chat) and API gateway |
| Flight Plan | 8003 | IFR flight plan generation (flightplandatabase.com, with local fallback) |
| Weather | 8004 | METAR, TAF, and ATIS generation |
| ASR | 8006 | Whisper transcription + callsign correction |
| Orchestrator | 8007 (container listens on 8006) | Agent routing, aircraft state machine, dispatch, debrief |
| Arrival Simulator | 8008 | Spawns AI arrivals on the ILS, drives vacate sequences |

The three ATC pilot agents (**DEL**, **GND**, **TWR** — see [agents.md](agents.md)) are not in
`docker-compose.yml`; they are deployed independently to **Google Cloud Run** and reached via
`DEL_AGENT_URL` / `GND_AGENT_URL` / `TWR_AGENT_URL`.

### Infrastructure

| Component | Image | Port (host:container) |
|---|---|---|
| PostgreSQL | `postgres:15-alpine` | 5432:5432 |
| Redis | `redis:7-alpine` | 6379:6379 |
| InfluxDB | `influxdb:2.7-alpine` | 8087:8086 |

### Placeholder / not-wired-up services (under `services/`, no page — don't expect real code)

| Directory | State |
|---|---|
| `services/analytics_service/` | Empty — only a `.gitkeep` |
| `services/nlp_service/` | Empty — only a `.gitkeep` |
| `services/tts_service/` | Empty — only a `.gitkeep` (TTS today is X-Plane's built-in speech, driven from `xplane_plugin/services/hmi_service.py` + `utils`) |
| `services/xplane_manager/` | Empty — only a `.gitkeep` |
| `services/database/` | Only `redis/test_redis.py`, a scratch script exercising basic Redis get/set/hset — not a service |
| `services/pilots_communication/` | Has real code (`main.py`, `router.py`, `config.py` — a `/process` endpoint that transcribes audio via a `transcription` service and forwards to a DEL/GND/TWR agent's `/tasks/send`), but it is **not** listed in `docker-compose.yml` and is not part of the active pipeline described in [architecture.md](architecture.md). Looks like an earlier prototype of what `asr_service` + `orchestrator_service` now do together. |

## Related

[architecture.md](architecture.md) · [agents.md](agents.md) · [shared.md](shared.md) · [xplane.md](xplane.md) · [data-and-testing.md](data-and-testing.md)
