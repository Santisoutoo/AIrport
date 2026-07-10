# Flight Plan Service

**Port 8003:8000** · [`services/flight_plan_service/`](../../services/flight_plan_service/) · IFR
flight plan generation. Health: `/api/v1/flight-plan/health`. Backed by PostgreSQL. See
[architecture](../architecture.md).

## What it does

Generates and stores the IFR flight plans that give every aircraft its identity (callsign,
route, levels). With a `FLIGHT_PLAN_GENERATOR_KEY` it uses flightplandatabase.com; without
one it falls back to a local generator.

| Relations | Modules |
|---|---|
| **Called by** | [Orchestrator](orchestrator_service.md) · [Arrival Simulator](arrival_simulator_service.md) · [Controller HMI](controller_hmi_service.md) · X-Plane plugin |
| **Calls** | PostgreSQL (`flight_plans`) · flightplandatabase.com (external) |

**Try it standalone:** <http://localhost:8003/docs> · health `GET /api/v1/flight-plan/health`.

## Responsibility

Generate IFR flight plans (routes, SIDs/STARs, levels) for aircraft, sourced from
**flightplandatabase.com** with a local generator fallback, and persist them.

## Layout

| Path | Role |
|---|---|
| [`core/api_generator.py`](../../services/flight_plan_service/core/api_generator.py) | Generates plans via the flightplandatabase.com API |
| [`core/generator.py`](../../services/flight_plan_service/core/generator.py) | Local generation fallback |
| [`core/data.py`](../../services/flight_plan_service/core/data.py) | Static/reference data |
| [`core/database/`](../../services/flight_plan_service/core/database/) | `connection.py`, `models.py`, `repositories/flight_plan.py` |
| [`models/schemas.py`](../../services/flight_plan_service/models/schemas.py) | Pydantic schemas |
| [`api/`](../../services/flight_plan_service/api/) | FastAPI routers |

## Consumers

Consumed by the [orchestrator](orchestrator_service.md) (aircraft identification + agent context),
the [arrival simulator](arrival_simulator_service.md) (`FLIGHT_PLAN_SERVICE_URL`), the
[HMI](controller_hmi_service.md), and the X-Plane plugin
([`xplane_plugin/services/flight_plan_service.py`](../../xplane_plugin/services/flight_plan_service.py)).

## Related
[architecture](../architecture.md) · [orchestrator](orchestrator_service.md) · [arrival_simulator](arrival_simulator_service.md)
