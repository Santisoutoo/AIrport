# Weather Service

**Port 8004:8000** · [`services/weather_service/`](../../services/weather_service/) · METAR, TAF
and ATIS. Health: `/api/v1/weather/health`. Backed by PostgreSQL. See [architecture](../architecture.md).

## Responsibility

Fetch real weather (METAR/TAF) and generate the **ATIS** broadcast used by the ATC agents and HMI.

## Layout

| Path | Role |
|---|---|
| [`main.py`](../../services/weather_service/main.py) | FastAPI entrypoint |
| [`api/routes.py`](../../services/weather_service/api/routes.py) | Weather / ATIS endpoints |
| [`core/metar_taf_fetcher.py`](../../services/weather_service/core/metar_taf_fetcher.py) | Fetches METAR/TAF from external sources |
| [`metar_taf.py`](../../services/weather_service/metar_taf.py) | METAR/TAF parsing helpers |
| [`core/atis_generator.py`](../../services/weather_service/core/atis_generator.py) | Builds the ATIS broadcast text |
| [`core/database/`](../../services/weather_service/core/database/) | `connection.py`, `models.py`, `repositories/atis.py` (persist ATIS) |
| [`models/schemas.py`](../../services/weather_service/models/schemas.py) | Pydantic request/response schemas |

## Consumers

The [orchestrator](orchestrator_service.md) pulls weather (its `api/weather.py` passthrough) to
provide agents with conditions; the [HMI](controller_hmi_service.md) shows ATIS.

## Related
[architecture](../architecture.md) · [orchestrator](orchestrator_service.md) · [flight_plan](flight_plan_service.md)
