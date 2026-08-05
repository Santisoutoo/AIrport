"""Compute and dispatch a full taxi plan (pushback + taxi legs).

Two public entry points:

- `compute_taxi_route(destination, via, callsign)`: ADK-tool-compatible
  helper that runs A* given a destination token and a list of controller
  via-points, using the current aircraft position from Redis. Returns the
  same dict shape `services/orchestrator_service/agent/tools/taxi_route.py`
  expects.

- `dispatch_taxi_plan(clearance_data, pilot_readback_text, *, registration,
  callsign)`: routes strictly on the controller's spoken taxiway sequence
  (issue #69), builds the two-leg plan (pushback -> waypoints), writes it
  to Redis for the plugin to consume, and emits a `hmi:chat` rejection
  when the issued sequence cannot be flown. The pilot readback never
  alters the route; a mismatch is only logged.
"""

import json
import logging
import random
import time
import uuid
from typing import Any, Optional, cast

from . import config
from .destination_parser import extract_destination
from .errors import RouteNotFoundError, UnknownTaxiwayError
from .hmi_chat import format_readback_rejected, publish_pilot_message
from .pushback import plan_pushback_leg
from .readback_parser import extract_taxiway_tokens, parse_pushback_direction

logger = logging.getLogger(__name__)


# -- Shared helpers (lazy imports so unit tests don't need redis/networkx) ----

def _get_redis_client() -> Any:
    # redis-py types the sync client as `Awaitable[T] | T`; keep it `Any`.
    import os
    import redis  # local import

    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", 6379))
    db = int(os.getenv("REDIS_DB", 0))
    return redis.Redis(host=host, port=port, db=db, decode_responses=True)


def _load_graph() -> Any:
    """Load the airport graph from Redis. Imports are kept local so the
    pure-Python modules in this package can be unit-tested standalone."""
    import sys
    from pathlib import Path

    # The graph module lives under plugins/GND, which is not a package.
    gnd_dir = Path(__file__).resolve().parents[3] / "plugins" / "GND"
    if str(gnd_dir) not in sys.path:
        sys.path.insert(0, str(gnd_dir))

    from graph import AirportGraph
    from shared.services.airport_data_store import AirportDataStore

    data = AirportDataStore().load()
    if data is None:
        raise RouteNotFoundError("airport graph not loaded in Redis")
    return AirportGraph(data=data)


def _aircraft_position(redis_client: Any, registration: str) -> Optional[tuple[float, float, float]]:
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


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _pushback_distance_from_apt(graph: Any, lat: float, lon: float) -> Optional[float]:
    """Find the nearest init/both taxi-route node (per apt.dat row 1201) and
    return the haversine distance to it. That's where X-Plane's ATC engine
    assumes an aircraft enters/exits the taxi network from a stand -- the
    right endpoint for pushback. Returns None when no such node is near."""
    best_dist: Optional[float] = None
    for node_id, data in graph.graph.nodes(data=True):
        usage = data.get("usage") or data.get("use")
        if usage not in ("init", "both"):
            continue
        if node_id not in graph._main_cc:
            continue
        d = _haversine_m(lat, lon, data["lat"], data["lon"])
        if best_dist is None or d < best_dist:
            best_dist = d
    return best_dist


# -- Public API ---------------------------------------------------------------

def compute_taxi_route(
    destination: str,
    via: list[str],
    callsign: str,
) -> dict:
    """Route over the taxiway graph from the aircraft's live position.

    When the controller named via taxiways, the route follows them strictly
    (issue #69): each leg runs only on edges of the authorized taxiway and an
    infeasible sequence fails instead of being silently re-routed. With no
    vias (destination-only clearance) the lenient A* is used and the result
    is tagged `"strict": False`.

    Mirrors the contract expected by
    `services/orchestrator_service/agent/tools/taxi_route.py`:
      success -> {"success": True, "waypoints": [...], "taxiway_sequence": [...],
                 "total_distance_m": float, "start": {...}, "end": {...}}
      failure -> {"success": False, "error": "..."}
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
    via = list(via or [])
    if via:
        return cast(dict, graph.find_route_strict_from_position(
            start_lat=lat, start_lon=lon,
            sequence=via, destination_token=destination,
        ))
    result = graph.find_route_from_position(
        start_lat=lat, start_lon=lon,
        end_token=destination, via=[],
    )
    if result.get("success"):
        result["strict"] = False
    return cast(dict, result)


def dispatch_taxi_plan(
    clearance_data: dict,
    pilot_readback_text: str,
    *,
    registration: str,
    controller_instruction: Optional[str] = None,
    callsign: Optional[str] = None,
    delay_range_s: Optional[tuple[float, float]] = None,
    taxi_speed_kts: Optional[float] = None,
    session_id: Optional[str] = None,
    redis_client: Any = None,
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

    # The controller's SPOKEN sequence is the single routing source of truth
    # (issue #69). The precomputed taxi_route attached to the clearance is
    # the output of an earlier A* run and is never used for routing again.
    controller_seq = extract_taxiway_tokens(
        None, fallback_text=controller_instruction or "",
        known_tokens=known_tokens, dedup=False,
    )

    # Destination comes ONLY from what the controller said. The DB's
    # runway_in_use is not consulted. When the controller doesn't state
    # an endpoint, the route ends at the last spoken taxiway.
    destination = (
        extract_destination(controller_instruction or "")
        or extract_destination(pilot_readback_text or "")
    )
    if destination:
        dest_upper = destination.upper()
        controller_seq = [t for t in controller_seq if t.upper() != dest_upper]
    elif controller_seq:
        destination = controller_seq[-1]
        controller_seq = controller_seq[:-1]

    # A clearance can carry pushback, taxi, or both. Three legitimate cases:
    #   - pushback only             -> one pushback leg
    #   - pushback + taxi via X     -> pushback + waypoints
    #   - taxi only (follow-up)     -> waypoints leg, no pushback
    pushback_approved = bool(taxi_data.get("pushback_approved")) if isinstance(taxi_data, dict) else False
    has_taxi_clearance = bool(controller_seq) or bool(destination)
    pushback_dir = parse_pushback_direction(instruction_text)
    delay = random.uniform(*delay_range)

    if pushback_approved and not has_taxi_clearance:
        apt_dist = _pushback_distance_from_apt(graph, stand_lat, stand_lon)
        pushback_leg = plan_pushback_leg(
            stand_lat=stand_lat, stand_lon=stand_lon, stand_heading_deg=stand_hdg,
            direction_deg=pushback_dir,
            override_distance_m=apt_dist,
        )
        pushback_eta = pushback_leg.distance_m / max(0.5, pushback_leg.speed_kts * 0.514444)
        ttl = int(delay + pushback_eta + 60.0)
        plan = {
            "version": 2,
            "plan_id": str(uuid.uuid4()),
            "started_at": time.time(),
            "delay_before_start_s": round(delay, 2),
            "legs": [pushback_leg.to_dict()],
        }
        key = config.MOVE_CMD_KEY.format(registration=registration)
        r.set(key, json.dumps(plan), ex=ttl)
        logger.info(
            "[taxi_router] dispatched pushback-only %s for %s: delay=%.1fs pushback=%.1fm face=%.0f",
            plan["plan_id"], registration, delay, pushback_leg.distance_m,
            pushback_leg.final_heading_deg,
        )
        return {"success": True, "plan_id": plan["plan_id"], "ttl_s": ttl, "legs": 1}

    if not has_taxi_clearance:
        return {"success": False, "error": "no taxi clearance and no pushback"}

    # The pilot readback never alters the flown route: it is only compared
    # against the controller sequence and a mismatch is logged for debrief.
    if readback_via and readback_via != list(dict.fromkeys(controller_seq)):
        logger.warning(
            "[taxi_router] readback mismatch for %s: controller=%s readback=%s",
            registration, controller_seq, readback_via,
        )

    strict = bool(controller_seq)
    if strict:
        route_result = graph.find_route_strict_from_position(
            start_lat=stand_lat, start_lon=stand_lon,
            sequence=controller_seq, destination_token=destination,
        )
    else:
        # Destination-only clearance ("taxi to runway 24L"): there is no
        # sequence to follow strictly, so fall back to the lenient A* and
        # tag the plan explicitly.
        route_result = graph.find_route_from_position(
            start_lat=stand_lat, start_lon=stand_lon,
            end_token=destination, via=[],
        )
    if not route_result.get("success"):
        reason_detail = route_result.get("error", "route unavailable")
        logger.warning(
            "[taxi_router] route rejected for %s seq=%s dest=%s strict=%s: %s",
            registration, controller_seq, destination, strict, reason_detail,
        )
        short_reason = _shorten_reason(reason_detail, controller_seq, readback_via)
        _reject(
            r, callsign=callsign, registration=registration,
            reason=short_reason, session_id=session_id,
        )
        return {"success": False, "error": reason_detail, "reason_to_pilot_chat": True}

    waypoints = route_result["waypoints"]
    if not waypoints:
        return {"success": False, "error": "empty route"}

    legs: list[dict] = []
    pushback_dist = 0.0
    pushback_eta = 0.0
    if pushback_approved:
        apt_dist = _pushback_distance_from_apt(graph, stand_lat, stand_lon)
        first = waypoints[0]
        pushback_leg = plan_pushback_leg(
            stand_lat=stand_lat, stand_lon=stand_lon, stand_heading_deg=stand_hdg,
            first_wp_lat=first["lat"], first_wp_lon=first["lon"],
            direction_deg=pushback_dir,
            override_distance_m=apt_dist,
        )
        legs.append(pushback_leg.to_dict())
        pushback_dist = pushback_leg.distance_m
        pushback_eta = pushback_leg.distance_m / max(0.5, pushback_leg.speed_kts * 0.514444)

    legs.append({
        "mode": "waypoints",
        "waypoints": waypoints,
        "taxiway_sequence": route_result.get("taxiway_sequence", []),
        "speed_kts": taxi_speed,
        "stop_at_end": True,
    })

    speed_mps = max(0.5, taxi_speed * 0.514444)
    taxi_eta = float(route_result["total_distance_m"]) / speed_mps
    ttl = int(delay + pushback_eta + taxi_eta + 60.0)

    plan = {
        "version": 2,
        "plan_id": str(uuid.uuid4()),
        "started_at": time.time(),
        "delay_before_start_s": round(delay, 2),
        "strict": strict,
        "legs": legs,
    }

    key = config.MOVE_CMD_KEY.format(registration=registration)
    r.set(key, json.dumps(plan), ex=ttl)
    logger.info(
        "[taxi_router] dispatched plan %s for %s: delay=%.1fs pushback=%.1fm taxi=%dwp dest=%s legs=%d strict=%s",
        plan["plan_id"], registration, delay, pushback_dist,
        len(waypoints), destination, len(legs), strict,
    )
    return {"success": True, "plan_id": plan["plan_id"], "ttl_s": ttl, "legs": len(legs)}


# -- Internal -----------------------------------------------------------------

def _shorten_reason(
    detail: str,
    controller_via: list[str],
    pilot_via: list[str],
) -> str:
    """Map a graph-layer error string to a pilot-facing phrase."""
    import re

    low = detail.lower()
    # Strict-routing failures (issue #70): the pilot names the exact problem
    # so the trainee controller can re-issue a valid clearance.
    m = re.search(r"unknown taxiway '([^']+)'", detail)
    if m:
        return f"taxiway {m.group(1)} not available"
    m = re.search(r"sequence not connected: (\S+) -> (\S+)", detail)
    if m:
        return f"taxiways {m.group(1)} and {m.group(2)} are not connected"
    m = re.search(r"no path from start to taxiway '([^']+)'", detail)
    if m:
        return f"unable to reach taxiway {m.group(1)}"
    if "destination too far from taxiway" in low or (
        "destination not reachable along taxiway" in low
    ):
        return "the issued route does not reach the destination"
    # Lenient-routing failures (legacy phrasing)
    if "via point" in low:
        # Try to extract the offending token
        for tok in pilot_via + controller_via:
            if f"'{tok}'" in detail or f"{tok!r}" in detail:
                return f"taxiway {tok} not found"
        return "requested taxiway not found"
    if "no path" in low:
        return "no route available"
    if "no connected node" in low:
        return "position off the movement area"
    return "unable to comply"


def _reject(
    redis_client: Any,
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
