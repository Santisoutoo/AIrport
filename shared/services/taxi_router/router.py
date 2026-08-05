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
from dataclasses import dataclass, field
from typing import Any, Optional, cast

from ..geo import KT_TO_MPS, haversine
from . import config
from .destination_parser import extract_destination
from .errors import RouteNotFoundError, UnknownTaxiwayError
from .hmi_chat import format_readback_rejected, publish_pilot_message
from .pushback import PushbackLeg, plan_pushback_leg
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
        d = haversine(lat, lon, data["lat"], data["lon"])
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
    r = redis_client or _get_redis_client()

    # Phase 1 -- parse and validate everything the plan is built from.
    ctx, error = _prepare_dispatch(
        r, clearance_data, pilot_readback_text,
        registration=registration, callsign=callsign,
        controller_instruction=controller_instruction,
        delay_range_s=delay_range_s, taxi_speed_kts=taxi_speed_kts,
        session_id=session_id,
    )
    if error is not None:
        return error
    # `_prepare_dispatch` returns a context whenever it returns no error.
    ctx = cast(DispatchContext, ctx)

    # Phase 2 -- a pushback-only clearance never reaches the router.
    clearance = ctx.clearance
    if clearance.pushback_approved and not clearance.has_taxi_clearance:
        return _dispatch_pushback_only(r, ctx)
    if not clearance.has_taxi_clearance:
        return {"success": False, "error": "no taxi clearance and no pushback"}

    _log_readback_mismatch(ctx)

    # Phase 3 -- resolve the route the controller issued, or say unable.
    route_result = _resolve_route(ctx)
    if not route_result.get("success"):
        return _reject_route(r, ctx, route_result)
    if not route_result["waypoints"]:
        return {"success": False, "error": "empty route"}

    # Phase 4 -- assemble the legs and publish the plan.
    return _dispatch_taxi_legs(r, ctx, route_result)


# -- Phase 1: input parsing and validation ------------------------------------

@dataclass(frozen=True)
class Stand:
    """Where the aircraft physically is when the clearance is dispatched."""
    lat: float
    lon: float
    heading_deg: float


@dataclass(frozen=True)
class TaxiClearance:
    """What the controller issued, distilled from the spoken instruction.

    `controller_seq` is the authorized taxiway sequence with the destination
    token already removed; `readback_via` is what the pilot echoed back and is
    never used for routing (issue #69), only for the mismatch warning.
    """
    controller_seq: list[str] = field(default_factory=list)
    destination: Optional[str] = None
    readback_via: list[str] = field(default_factory=list)
    pushback_approved: bool = False
    pushback_dir: Optional[float] = None

    @property
    def has_taxi_clearance(self) -> bool:
        """A clearance can carry pushback, taxi, or both. Three legitimate
        cases: pushback only -> one pushback leg; pushback + taxi via X ->
        pushback + waypoints; taxi only (follow-up) -> waypoints, no pushback.
        """
        return bool(self.controller_seq) or bool(self.destination)

    @property
    def strict(self) -> bool:
        """True when there is a spoken sequence to follow edge by edge."""
        return bool(self.controller_seq)


@dataclass(frozen=True)
class DispatchContext:
    """Everything phase 1 resolves before any routing happens: where the
    aircraft is, which graph to route on, what the controller cleared, and
    the timing/identity parameters the plan is stamped with."""
    stand: Stand
    graph: Any
    clearance: TaxiClearance
    registration: str
    callsign: str
    delay: float
    taxi_speed: float
    session_id: Optional[str] = None


def _prepare_dispatch(
    redis_client: Any,
    clearance_data: dict,
    pilot_readback_text: str,
    *,
    registration: str,
    callsign: Optional[str],
    controller_instruction: Optional[str],
    delay_range_s: Optional[tuple[float, float]],
    taxi_speed_kts: Optional[float],
    session_id: Optional[str],
) -> tuple[Optional[DispatchContext], Optional[dict]]:
    """Resolve the dispatch context, or the failure dict that aborts it.

    Returns `(context, None)` on success and `(None, error)` when the aircraft
    has no live position or the airport graph is not loaded -- the two states
    in which no plan can be produced at all.
    """
    callsign = callsign or clearance_data.get("aircraft_registration") or registration
    delay_range = delay_range_s or (config.DELAY_MIN_S, config.DELAY_MAX_S)
    taxi_speed = float(taxi_speed_kts or config.TAXI_SPEED_KTS)

    pos = _aircraft_position(redis_client, registration)
    if pos is None:
        logger.warning("[taxi_router] no live position for %s", registration)
        return None, {"success": False, "error": "no live position"}

    try:
        graph = _load_graph()
    except RouteNotFoundError as exc:
        logger.error("[taxi_router] graph load failed: %s", exc)
        return None, {"success": False, "error": str(exc)}

    clearance = _parse_clearance(
        clearance_data, pilot_readback_text,
        controller_instruction=controller_instruction,
        known_tokens=list(graph._nodes_by_taxiway.keys()),
    )
    return DispatchContext(
        stand=Stand(*pos),
        graph=graph,
        clearance=clearance,
        registration=registration,
        callsign=callsign,
        delay=random.uniform(*delay_range),
        taxi_speed=taxi_speed,
        session_id=session_id,
    ), None


def _parse_clearance(
    clearance_data: dict,
    pilot_readback_text: str,
    *,
    controller_instruction: Optional[str],
    known_tokens: list[str],
) -> TaxiClearance:
    """Distil the controller instruction (and the readback) into a clearance."""
    taxi_data = (clearance_data or {}).get("taxi_data") or {}
    spoken_route = taxi_data.get("taxi_route") if isinstance(taxi_data, dict) else None
    instruction_text = (
        (taxi_data or {}).get("instruction_text")
        or clearance_data.get("instruction_text")
        or pilot_readback_text
        or ""
    )

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

    return TaxiClearance(
        controller_seq=controller_seq,
        destination=destination,
        readback_via=readback_via,
        pushback_approved=(
            bool(taxi_data.get("pushback_approved")) if isinstance(taxi_data, dict) else False
        ),
        pushback_dir=parse_pushback_direction(instruction_text),
    )


def _log_readback_mismatch(ctx: DispatchContext) -> None:
    """The pilot readback never alters the flown route: it is only compared
    against the controller sequence and a mismatch is logged for debrief."""
    clearance = ctx.clearance
    if clearance.readback_via and clearance.readback_via != list(
        dict.fromkeys(clearance.controller_seq)
    ):
        logger.warning(
            "[taxi_router] readback mismatch for %s: controller=%s readback=%s",
            ctx.registration, clearance.controller_seq, clearance.readback_via,
        )


# -- Phase 3: route resolution ------------------------------------------------

def _resolve_route(ctx: DispatchContext) -> dict:
    """Run the strict router on the spoken sequence, or the lenient A* when
    the controller only named a destination ("taxi to runway 24L")."""
    stand, clearance = ctx.stand, ctx.clearance
    if clearance.strict:
        return cast(dict, ctx.graph.find_route_strict_from_position(
            start_lat=stand.lat, start_lon=stand.lon,
            sequence=clearance.controller_seq,
            destination_token=clearance.destination,
        ))
    return cast(dict, ctx.graph.find_route_from_position(
        start_lat=stand.lat, start_lon=stand.lon,
        end_token=clearance.destination, via=[],
    ))


def _reject_route(redis_client: Any, ctx: DispatchContext, route_result: dict) -> dict:
    """Log the routing failure and make the simulated pilot say unable."""
    clearance = ctx.clearance
    reason_detail = route_result.get("error", "route unavailable")
    logger.warning(
        "[taxi_router] route rejected for %s seq=%s dest=%s strict=%s: %s",
        ctx.registration, clearance.controller_seq, clearance.destination,
        clearance.strict, reason_detail,
    )
    short_reason = _shorten_reason(
        reason_detail, clearance.controller_seq, clearance.readback_via,
    )
    _reject(
        redis_client, callsign=ctx.callsign, registration=ctx.registration,
        reason=short_reason, session_id=ctx.session_id,
    )
    return {"success": False, "error": reason_detail, "reason_to_pilot_chat": True}


# -- Phase 4: leg assembly and publication ------------------------------------

def _plan_pushback(ctx: DispatchContext, first_wp: Optional[dict] = None) -> PushbackLeg:
    """Pushback leg aimed at `first_wp` when a taxi clearance follows, or a
    plain back-out when it doesn't. The distance is capped by the nearest
    apt.dat init/both node -- where X-Plane assumes the taxi network starts."""
    stand = ctx.stand
    return plan_pushback_leg(
        stand_lat=stand.lat, stand_lon=stand.lon, stand_heading_deg=stand.heading_deg,
        first_wp_lat=first_wp["lat"] if first_wp else None,
        first_wp_lon=first_wp["lon"] if first_wp else None,
        direction_deg=ctx.clearance.pushback_dir,
        override_distance_m=_pushback_distance_from_apt(ctx.graph, stand.lat, stand.lon),
    )


def _eta_s(distance_m: float, speed_kts: float) -> float:
    """Seconds to cover `distance_m`, with a floor on the speed."""
    return distance_m / max(0.5, speed_kts * KT_TO_MPS)


def _build_plan(delay: float, legs: list[dict], *, strict: Optional[bool] = None) -> dict:
    plan = {
        "version": 2,
        "plan_id": str(uuid.uuid4()),
        "started_at": time.time(),
        "delay_before_start_s": round(delay, 2),
    }
    if strict is not None:
        plan["strict"] = strict
    plan["legs"] = legs
    return plan


def _store_plan(redis_client: Any, registration: str, plan: dict, ttl: int) -> None:
    key = config.MOVE_CMD_KEY.format(registration=registration)
    redis_client.set(key, json.dumps(plan), ex=ttl)


def _dispatch_pushback_only(redis_client: Any, ctx: DispatchContext) -> dict:
    """Publish the single-leg plan for a "pushback approved" with no taxi."""
    pushback_leg = _plan_pushback(ctx)
    ttl = int(ctx.delay + _eta_s(pushback_leg.distance_m, pushback_leg.speed_kts) + 60.0)
    plan = _build_plan(ctx.delay, [pushback_leg.to_dict()])
    _store_plan(redis_client, ctx.registration, plan, ttl)
    logger.info(
        "[taxi_router] dispatched pushback-only %s for %s: delay=%.1fs pushback=%.1fm face=%.0f",
        plan["plan_id"], ctx.registration, ctx.delay, pushback_leg.distance_m,
        pushback_leg.final_heading_deg,
    )
    return {"success": True, "plan_id": plan["plan_id"], "ttl_s": ttl, "legs": 1}


def _dispatch_taxi_legs(redis_client: Any, ctx: DispatchContext, route_result: dict) -> dict:
    """Publish the taxi plan: an optional pushback leg followed by the
    waypoints leg, with a TTL covering the whole maneuver."""
    waypoints = route_result["waypoints"]

    legs: list[dict] = []
    pushback_dist = 0.0
    pushback_eta = 0.0
    if ctx.clearance.pushback_approved:
        pushback_leg = _plan_pushback(ctx, first_wp=waypoints[0])
        legs.append(pushback_leg.to_dict())
        pushback_dist = pushback_leg.distance_m
        pushback_eta = _eta_s(pushback_leg.distance_m, pushback_leg.speed_kts)

    legs.append({
        "mode": "waypoints",
        "waypoints": waypoints,
        "taxiway_sequence": route_result.get("taxiway_sequence", []),
        "speed_kts": ctx.taxi_speed,
        "stop_at_end": True,
    })

    taxi_eta = _eta_s(float(route_result["total_distance_m"]), ctx.taxi_speed)
    ttl = int(ctx.delay + pushback_eta + taxi_eta + 60.0)

    plan = _build_plan(ctx.delay, legs, strict=ctx.clearance.strict)
    _store_plan(redis_client, ctx.registration, plan, ttl)
    logger.info(
        "[taxi_router] dispatched plan %s for %s: delay=%.1fs pushback=%.1fm taxi=%dwp dest=%s legs=%d strict=%s",
        plan["plan_id"], ctx.registration, ctx.delay, pushback_dist,
        len(waypoints), ctx.clearance.destination, len(legs), ctx.clearance.strict,
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
