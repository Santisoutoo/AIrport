# X-Plane integration

Two parts: the **in-sim plugin** ([`xplane_plugin/`](../xplane_plugin/)) that runs inside X-Plane
12 via XPPython3, and the **deployable plugin files** ([`plugins/`](../plugins/)) that you copy
into the simulator. See [architecture](architecture.md) for where this sits in the pipeline.

## `plugins/` — what you install into X-Plane

Per [`README.md`](../README.md), copy these into
`<X-Plane 12>/Resources/plugins/PythonPlugins/`:

| Path | Role |
|---|---|
| [`plugins/PI_spawn_obj.py`](../plugins/PI_spawn_obj.py) | XPPython3 plugin entry (`PI_` prefix) — spawns aircraft objects in the sim |
| [`plugins/GND/`](../plugins/GND/) | Ground routing: `data_parser`, `graph`, `models.py` — parses the airport and builds the taxi graph used in-sim |

Dependencies are installed into X-Plane's bundled Python via
[`docs/install/install_dependencies.bat`](../docs/install/install_dependencies.bat) (wraps
[`install_xppython3.ps1`](../docs/install/install_xppython3.ps1)).

## `xplane_plugin/` — plugin source (development tree)

| Path | Role |
|---|---|
| [`services/aircraft_mover.py`](../xplane_plugin/services/aircraft_mover.py) | Moves aircraft along the dispatched multi-leg plan (emits phase strings like `pushback`, `taxi_out`, `holding` — matches [`shared/models/phases.py`](../shared/models/phases.py)) |
| [`services/aircraft_spawner.py`](../xplane_plugin/services/aircraft_spawner.py) | Spawns aircraft objects |
| [`services/aircraft_obj_mapper.py`](../xplane_plugin/services/aircraft_obj_mapper.py) | Maps aircraft types → X-Plane objects |
| [`services/airport_service.py`](../xplane_plugin/services/airport_service.py) | Airport data access in-sim |
| [`services/flight_plan_service.py`](../xplane_plugin/services/flight_plan_service.py) | Talks to the [flight plan service](services/flight_plan_service.md) |
| [`services/hmi_service.py`](../xplane_plugin/services/hmi_service.py) | Talks to the [HMI](services/controller_hmi_service.md); drives readback speech (X-Plane built-in TTS) |
| [`services/user_service.py`](../xplane_plugin/services/user_service.py) | User/session helpers |
| [`airport_plugin/PI_userInterface.py`](../xplane_plugin/airport_plugin/PI_userInterface.py) | In-sim UI plugin |
| [`ui/windows_manager.py`](../xplane_plugin/ui/windows_manager.py) | Manages plugin windows |
| `communication/`, `xplane_integration/`, `utils/`, `images/` | Support packages |

There is a plugin-specific readme: [`xplane_plugin/PLUGIN_README.md`](../xplane_plugin/PLUGIN_README.md).

## How motion arrives

The orchestrator's [taxi_router](shared.md) computes an A\* route and calls `dispatch_taxi_plan`,
which pushes a multi-leg move plan (via Redis) that `aircraft_mover` consumes in-sim to move the
aircraft and advance its phase. TTS readback is spoken through X-Plane's built-in speech.

## Related
[index](index.md) · [architecture](architecture.md) · [shared](shared.md) · [orchestrator](services/orchestrator_service.md)
