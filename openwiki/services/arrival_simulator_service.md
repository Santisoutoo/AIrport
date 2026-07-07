# Arrival Simulator Service

**Port 8008:8000** · [`services/arrival_simulator_service/`](../../services/arrival_simulator_service/) ·
spawns AI arrivals on the ILS and drives them to vacate. Health: `/api/v1/arrivals/health`. See
[architecture](../architecture.md).

## Responsibility

Continuously spawn AI arrival traffic (on the ILS), drive each aircraft through the arrival phases
(`approach → short_final → landing_roll → vacating → taxi_in`), and publish lifecycle events so the
[orchestrator](orchestrator_service.md) can handle the handoff to GND. Interval configured by
`ARRIVAL_INTERVAL_S` (default 120s).

## Layout

| Path | Role |
|---|---|
| [`main.py`](../../services/arrival_simulator_service/main.py) | FastAPI entrypoint + scheduler startup |
| [`api/routes.py`](../../services/arrival_simulator_service/api/routes.py) | Arrivals endpoints |
| [`core/scheduler.py`](../../services/arrival_simulator_service/core/scheduler.py) | Periodic spawn loop (maintains concurrent arrivals) |
| [`core/arrival_planner.py`](../../services/arrival_simulator_service/core/arrival_planner.py) | Plans an arrival (route to threshold, phase timeline) |
| [`core/plan_catalog.py`](../../services/arrival_simulator_service/core/plan_catalog.py) | Catalog of arrival plans |
| [`core/runway_config.py`](../../services/arrival_simulator_service/core/runway_config.py) | Active runway / approach config |
| [`core/event_bridge.py`](../../services/arrival_simulator_service/core/event_bridge.py) | Publishes arrival lifecycle events (Redis) to the orchestrator |
| `core/phases.py`, `core/geo.py` | Phase timeline + geographic helpers |

## Integrations

`REDIS_URL`, `FLIGHT_PLAN_SERVICE_URL`, `HMI_SERVICE_URL`, `ORCHESTRATOR_SERVICE_URL` (see the
`environment:` block in [`docker-compose.yml`](../../docker-compose.yml)). Handoff lands in the
orchestrator via [`api/arrivals.py`](../../services/orchestrator_service/api/arrivals.py) +
`advance_to_gnd_arrival`.

## Tests

[`tests/unit/arrival_simulator/`](../../tests/unit/arrival_simulator/) (event bridge),
[`tests/arrivals/`](../../tests/arrivals/) (planner, phases, runway config, geo),
[`tests/integration/test_arrival_pipeline.py`](../../tests/integration/test_arrival_pipeline.py).

## Related
[architecture](../architecture.md) · [orchestrator](orchestrator_service.md) · [flight_plan](flight_plan_service.md) · [data-and-testing](../data-and-testing.md)
