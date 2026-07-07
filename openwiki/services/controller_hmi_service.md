# Controller HMI Service

**Port 8005:8000** · [`services/controller_hmi_service/`](../../services/controller_hmi_service/) ·
the web UI a human controller uses, and the API gateway to the rest of the system. Health:
`/api/v1/hmi/health`. Open at [http://localhost:8005](http://localhost:8005). See
[architecture](../architecture.md).

## Responsibility

Serve the controller-facing web app — **flight strips, ground radar, ATIS, chat/push-to-talk** —
and proxy requests to [ASR](asr_service.md), [orchestrator](orchestrator_service.md),
[flight plan](flight_plan_service.md) and [weather](weather_service.md). Talks to Postgres and
Redis directly for state it needs to render.

## Layout

| Path | Role |
|---|---|
| [`main.py`](../../services/controller_hmi_service/main.py) | FastAPI entrypoint; mounts static app |
| [`api/routes.py`](../../services/controller_hmi_service/api/routes.py) | Main HMI endpoints (strips, radar state) |
| [`api/chat.py`](../../services/controller_hmi_service/api/chat.py) | Chat / transmission endpoint → ASR → orchestrator |
| [`api/plugin_routes.py`](../../services/controller_hmi_service/api/plugin_routes.py) | Endpoints the X-Plane plugin calls |
| [`api/auth.py`](../../services/controller_hmi_service/api/auth.py) | Auth |
| [`api/models.py`](../../services/controller_hmi_service/api/models.py) | Pydantic models |
| `static/` | Front-end assets (served UI) |

## Integrations

Env: `REDIS_URL`, `DB_*` (Postgres), `ASR_URL`, `ORCHESTRATOR_URL`. Depends (Compose healthchecks)
on postgres, redis, flight_plan, weather. The plugin reaches it via
[`xplane_plugin/services/hmi_service.py`](../../xplane_plugin/services/hmi_service.py).

## Tests

HMI chat routing is exercised in [`tests/taxi_router/test_hmi_chat.py`](../../tests/taxi_router/test_hmi_chat.py).

## Related
[architecture](../architecture.md) · [asr](asr_service.md) · [orchestrator](orchestrator_service.md) · [xplane](../xplane.md)
