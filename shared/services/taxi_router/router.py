"""Compute and dispatch a full taxi plan (pushback + taxi legs).

Two public entry points:

- `compute_taxi_route(destination, via, callsign)`: ADK-tool-compatible
  helper that runs A* given a destination token and a list of controller
  via-points, using the current aircraft position from Redis. Returns the
  same dict shape `services/orchestrator_service/agent/tools/taxi_route.py`
  expects.

- `dispatch_taxi_plan(clearance_data, pilot_readback_text, *, registration,
  callsign)`: merges controller + pilot waypoints, builds the two-leg
  plan (pushback → waypoints), writes it to Redis for the plugin to
  consume, and emits a `hmi:chat` rejection when the readback cannot be
  routed.
"""

import json
import logging
import random
import time
import uuid
from typing import Optional

from . import config
from .constraints import merge_constraints
from .errors import RouteNotFoundError, UnknownTaxiwayError
from .hmi_chat import format_readback_rejected, publish_pilot_message
from .pushback import plan_pushback_leg
from .readback_parser import extract_taxiway_tokens, parse_pushback_direction

logger = logging.getLogger(__name__)


# -- Shared helpers (lazy imports so unit tests don't need redis/networkx) ----

def _get_redis_client():
    import os
    import redis  # local import

    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", 6379))
    db = int(os.getenv("REDIS_DB", 0))
    return redis.Redis(host=host, port=port, db=db, decode_responses=True)


def _load_graph():
    """Load the airport graph from Redis. Imports are kept local so the
    pure-Python modules in this package can be unit-tested standalone."""
    import sys
    from pathlib import Path

    # The graph module lives under plugins/GND, which is not a package.
    gnd_dir = Path(__file__).resolve().parents[3] / "plugins" / "GND"
    if str(gnd_dir) not in sys.path:
        sys.path.insert(0, str(gnd_dir))

    from graph import AirportGraph  # type: ignore
    from shared.services.airport_data_store import AirportDataStore  # type: ignore

    data = AirportDataStore().load()
    if data is None:
        raise RouteNotFoundError("airport graph not loaded in Redis")
    return AirportGraph(data=data)


def _aircraft_position(redis_client, registration: str) -> Optional[tuple[float, float, float]]:
    """Return (lat, lon, heading) from `aircraft:state:{reg}` or None."""
    state = redis_client.hgetall(f"aircraft:state:{registration}")
    if not state:
        return None
    try:
        return (
            float(state["latitude"]),
            float(state["longitude"]),
            float(state.get("heading", 0.0)),
        )
    except (KeyError, ValueError):
        return None


# -- Public API ---------------------------------------------------------------

def compute_taxi_route(
    destination: str,
    via: list[str],
    callsign: str,
) -> dict:
    """A* over the taxiway graph from the aircraft's live position.

    Mirrors the contract expected by
    `services/orchestrator_service/agent/tools/taxi_route.py`:
      success → {"success": True, "waypoints": [...], "taxiway_sequence": [...],
                 "total_distance_m": float, "start": {...}, "end": {...}}
      failure → {"success": False, "error": "..."}
    """
    try:
        r = _get_redis_client()
    except Exception as exc:
        return {"success": False, "error": f"redis unavailable: {exc}"}

    pos = _aircraft_position(r, callsign)
    if pos is None:
        return {"success": False, "error": f"no live position for {callsign!r}"}

    try:
        graph = _load_graph()
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    lat, lon, _hdg = pos
    result = graph.find_route_from_position(
        start_lat=lat, start_lon=lon,
        end_token=destination, via=list(via or []),
    )
    return result


def dispatch_taxi_plan(
    clearance_data: dict,
    pilot_readback_text: str,
    *,
    registration: str,
    callsign: Optional[str] = None,
    delay_range_s: Optional[tuple[float, float]] = None,
    taxi_speed_kts: Optional[float] = None,
    session_id: Optional[str] = None,
    redis_client=None,
) -> dict:
    """Build and publish the full taxi plan after GND has produced a readback.

    Returns a status dict:
      {"success": True, "plan_id": str, "ttl_s": int}
      {"success": False, "error": "...", "reason_to_pilot_chat": bool}
    """
    callsign = callsign or clearance_data.get("aircraft_registration") or registration
    delay_range = delay_range_s or (config.DELAY_MIN_S, config.DELAY_MAX_S)
    taxi_speed = float(taxi_speed_kts or config.TAXI_SPEED_KTS)

    r = redis_client or _get_redis_client()

    pos = _aircraft_position(r, registration)
    if pos is None:
        logger.warning("[taxi_router] no live position for %s", registration)
        return {"success": False, "error": "no live position"}
    stand_lat, stand_lon, stand_hdg = pos

    # Extract readback waypoints and pushback direction
    taxi_data = (clearance_data or {}).get("taxi_data") or {}
    spoken_route = taxi_data.get("taxi_route") if isinstance(taxi_data, dict) else None
    instruction_text = (
        (taxi_data or {}).get("instruction_text")
        or clearance_data.get("instruction_text")
        or pilot_readback_text
        or ""
    )

    try:
        graph = _load_graph()
    except RouteNotFoundError as exc:
        logger.error("[taxi_router] graph load failed: %s", exc)
        return {"success": False, "error": str(exc)}

    known_tokens = list(graph._nodes_by_taxiway.keys())
    readback_via = extract_taxiway_tokens(
        spoken_route, fallback_text=instruction_text,
        known_tokens=known_tokens,
    )

    # Controller via-points came from the precomputed taxi_route attached
    # to the GND clearance. Fall back to its taxiway_sequence.
    taxi_route = clearance_data.get("taxi_route") or {}
    controller_via = list(taxi_route.get("taxiway_sequence") or [])

    merged = merge_constraints(controller_via, readback_via)

    destination = taxi_data.get("runway_in_use") or clearance_data.get("runway_in_use")
    if not destination:
        msg = "no destination runway in clearance"
        logger.warning("[taxi_router] %s", msg)
        _reject(
            r, callsign=callsign, registration=registration,
            reason="no runway assigned", session_id=session_id,
        )
        return {"success": False, "error": msg, "reason_to_pilot_chat": True}

    # Run constrained A*
    route_result = graph.find_route_from_position(
        start_lat=stand_lat, start_lon=stand_lon,
        end_token=destination, via=merged,
    )
    if not route_result.get("success"):
        reason_detail = route_result.get("error", "route unavailable")
        logger.info(
            "[taxi_router] route rejected for %s via=%s dest=%s: %s",
            registration, merged, destination, reason_detail,
        )
        short_reason = _shorten_reason(reason_detail, merged, readback_via)
        _reject(
            r, callsign=callsign, registration=registration,
            reason=short_reason, session_id=session_id,
        )
        return {"success": False, "error": reason_detail, "reason_to_pilot_chat": True}

    waypoints = route_result["waypoints"]
    if not waypoints:
        return {"success": False, "error": "empty route"}

    first = waypoints[0]
    pushback_leg = plan_pushback_leg(
        stand_lat=stand_lat, stand_lon=stand_lon, stand_heading_deg=stand_hdg,
        first_wp_lat=first["lat"], first_wp_lon=first["lon"],
        direction_deg=parse_pushback_direction(instruction_text),
    )

    delay = random.uniform(*delay_range)
    speed_mps = max(0.5, taxi_speed * 0.514444)
    taxi_eta = float(route_result["total_distance_m"]) / speed_mps
    pushback_eta = pushback_leg.distance_m / max(0.5, pushback_leg.speed_kts * 0.514444)
    ttl = int(delay + pushback_eta + taxi_eta + 60.0)

    plan = {
        "version": 2,
        "plan_id": str(uuid.uuid4()),
        "started_at": time.time(),
        "delay_before_start_s": round(delay, 2),
        "legs": [
            pushback_leg.to_dict(),
            {
                "mode": "waypoints",
                "waypoints": waypoints,
                "taxiway_sequence": route_result.get("taxiway_sequence", []),
                "speed_kts": taxi_speed,
                "stop_at_end": True,
            },
        ],
    }

    key = config.MOVE_CMD_KEY.format(registration=registration)
    r.set(key, json.dumps(plan), ex=ttl)
    logger.info(
        "[taxi_router] dispatched plan %s for %s: delay=%.1fs pushback=%.1fm taxi=%dwp dest=%s",
        plan["plan_id"], registration, delay, pushback_leg.distance_m,
        len(waypoints), destination,
    )
    return {"success": True, "plan_id": plan["plan_id"], "ttl_s": ttl}


# -- Internal -----------------------------------------------------------------

def _shorten_reason(
    detail: str,
    merged_via: list[str],
    pilot_via: list[str],
) -> str:
    """Map a graph-layer error string to a pilot-facing phrase."""
    low = detail.lower()
    if "via point" in low:
        # Try to extract the offending token
        for tok in pilot_via + merged_via:
            if f"'{tok}'" in detail or f"{tok!r}" in detail:
                return f"taxiway {tok} not found"
        return "requested taxiway not found"
    if "no path" in low:
        return "no route available"
    if "no connected node" in low:
        return "position off the movement area"
    return "unable to comply"


def _reject(
    redis_client,
    *,
    callsign: str,
    registration: str,
    reason: str,
    session_id: Optional[str],
) -> None:
    text = format_readback_rejected(callsign, reason)
    try:
        publish_pilot_message(
            redis_client,
            callsign=callsign, registration=registration,
            kind="readback_rejected", text=text, session_id=session_id,
        )
    except Exception as exc:
        logger.error("[taxi_router] failed to publish rejection: %s", exc)
