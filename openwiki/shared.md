# Shared package (`shared/`)

Cross-service models and services imported by multiple microservices (the orchestrator, arrival
simulator, and tests all depend on it). Source under [`shared/`](../shared/). See
[architecture](architecture.md).

## Models — [`shared/models/`](../shared/models/)

| Module | Purpose |
|---|---|
| [`phases.py`](../shared/models/phases.py) | `Phase` enum + `ARRIVAL_PHASES` / `AIRBORNE_PHASES` sets. Drives the DEL→GND→TWR state machine (departure + arrival phase strings, lowercase to match the mover/state store) |
| [`aircraft.py`](../shared/models/aircraft.py) | Aircraft model |
| [`aircraft_state.py`](../shared/models/aircraft_state.py) | Aircraft state representation |
| [`airport.py`](../shared/models/airport.py) | Airport model |
| [`communications.py`](../shared/models/communications.py) | Communication / transmission model |
| [`command_parser.py`](../shared/models/command_parser.py) | Parses ATC commands |

## Services — [`shared/services/`](../shared/services/)

| Module | Purpose |
|---|---|
| [`taxi_router/`](../shared/services/taxi_router/) | **A\* taxi routing** package (see below) |
| [`aircraft_state_store.py`](../shared/services/aircraft_state_store.py) | Aircraft state persistence (Redis-backed): phase, position, per-aircraft records |
| [`aircraft_tracker.py`](../shared/services/aircraft_tracker.py) | Tracks live aircraft |
| [`airport_data_store.py`](../shared/services/airport_data_store.py) | Loads/serves airport data (taxiways, stands) |
| [`geo.py`](../shared/services/geo.py) | Geographic helpers (distance, bearings) |

## taxi_router (A\* routing)

[`shared/services/taxi_router/`](../shared/services/taxi_router/) computes A\* taxi routes with
controller/pilot constraints, plans the pushback leg, and dispatches multi-leg move commands to
the plugin. Public API ([`__init__.py`](../shared/services/taxi_router/__init__.py)):

| Symbol | Role |
|---|---|
| `compute_taxi_route` | A\* route over the airport taxiway graph |
| `dispatch_taxi_plan` | Sends the multi-leg move plan (to the plugin via Redis) |
| `plan_pushback_leg`, `PushbackLeg` | Pushback geometry before taxi |
| `extract_destination` | Regex parse of the destination (holding point / runway) from instruction text |
| `extract_taxiway_tokens`, `parse_pushback_direction` | Parse "via" taxiways & pushback direction from readback |
| `merge_constraints` | Merge controller + pilot constraints |
| Errors | `TaxiRouterError`, `UnknownTaxiwayError`, `RouteNotFoundError`, `InvalidPushbackError` |

The orchestrator's `get_taxi_route` tool
([`agent/tools/taxi_route.py`](../services/orchestrator_service/agent/tools/taxi_route.py)) wraps
this: it extracts destination + via taxiways from the raw instruction (so the LLM doesn't parse
them), loads the airport graph, and returns waypoints + taxiway sequence + total distance.

Well covered by tests under [`tests/taxi_router/`](../tests/taxi_router/) (graph construction,
token resolution, routing e2e, pushback leg).

## Related
[index](index.md) · [architecture](architecture.md) · [orchestrator](services/orchestrator_service.md) · [xplane](xplane.md)
