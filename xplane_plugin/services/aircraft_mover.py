"""Plugin-side consumer for taxi move commands.

Reads `aircraft:{reg}:move_cmd` JSON plans from Redis and drives the
spawned aircraft instances through a pushback → taxi → done state
machine. State updates (lat/lon/heading/speed/phase) are written back to
the AircraftStateStore so the HMI sees live movement.

Supported plan shapes:

1. v2 multi-leg (taxi_router dispatch):
   {"version":2,"plan_id":...,"started_at":...,"delay_before_start_s":...,
    "legs":[{"mode":"pushback",...},{"mode":"waypoints",...}]}

2. Legacy single-mode (test_move_taxiway.py / test_move_straight.py):
   {"mode":"waypoints","waypoints":[...],"speed_kts":...,"started_at":...}
   {"mode":"straight","heading":...,"speed_kts":...,"duration_s":...}
"""

import json
import time
from dataclasses import dataclass, field
from typing import Optional

from XPPython3 import xp

from ...shared.models.aircraft_state import AircraftState
from ...shared.models.phases import Phase
from ...shared.services.aircraft_state_store import AircraftStateStore
from ...shared.services.geo import (
    FT_TO_M,
)
from ...shared.services.geo import (
    KT_TO_MPS as _KT_TO_MPS,
)
from ...shared.services.geo import (
    advance as _advance,
)
from ...shared.services.geo import (
    bearing as _bearing,
)
from ...shared.services.geo import (
    haversine as _haversine,
)
from ...shared.services.geo import (
    shortest_angle as _shortest_angle,
)

_MOVE_CMD_PATTERN = "aircraft:*:move_cmd"
_SPAWN_REQUEST_PATTERN = "aircraft:spawn_request:*"
_STATE_FLUSH_INTERVAL_S = 0.5
_WAYPOINT_REACHED_M = 2.5
_FLARE_AGL_FT = 50.0
_LANDING_ROLL_STOP_KTS = 20.0


# -- Plan state --------------------------------------------------------------


@dataclass
class _PlanState:
    registration: str
    plan_id: str
    started_at: float
    delay_s: float
    legs: list[dict]

    # Current position we own (authoritative while plan is active)
    lat: float = 0.0
    lon: float = 0.0
    heading: float = 0.0

    # Vertical / airspeed state (used by approach + landing_roll legs)
    altitude_msl_ft: float = 0.0
    altitude_agl_ft: float = 0.0
    vertical_speed_fpm: float = 0.0
    ias_kts: float = 0.0
    on_ground: bool = True

    # State machine
    phase: str = "waiting"  # waiting → pushback → taxi → approach → landing_roll → vacating → taxi_in → done
    final_phase: str = "holding"  # phase used by _finalise on reached_end (parked for arrivals)
    leg_index: int = 0

    # Pushback bookkeeping
    pushback_start_lat: float = 0.0
    pushback_start_lon: float = 0.0
    pushback_start_heading: float = 0.0
    pushback_total_dist_m: float = 0.0
    pushback_traveled_m: float = 0.0
    pushback_sub_phase: str = "reverse"  # reverse → pivot → (leg advances)

    # Taxi bookkeeping
    wp_index: int = 0

    # Telemetry
    last_state_publish: float = 0.0
    events_emitted: set = field(default_factory=set)


# -- Main class --------------------------------------------------------------


class AircraftMover:
    """Drives spawned aircraft along multi-leg taxi plans."""

    def __init__(self, spawner, state_store: AircraftStateStore, redis_client=None):
        self._spawner = spawner
        self._store = state_store
        self._r = redis_client or self._make_redis()
        self._probe = None
        self._flight_loop_id = None
        self._scan_loop_id = None
        self._plans: dict[str, _PlanState] = {}
        self._running = False

    @staticmethod
    def _make_redis():
        import os

        import redis

        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", 6379))
        db = int(os.getenv("REDIS_DB", 0))
        return redis.Redis(host=host, port=port, db=db, decode_responses=True)

    # -- Lifecycle ----------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self._probe = xp.createProbe()
        self._flight_loop_id = xp.createFlightLoop(self._tick, phase=1)
        xp.scheduleFlightLoop(self._flight_loop_id, interval=-1)  # every frame
        self._scan_loop_id = xp.createFlightLoop(self._scan, phase=1)
        xp.scheduleFlightLoop(self._scan_loop_id, interval=1.0)
        self._running = True
        xp.log("AIrport Mover: started")

    def stop(self) -> None:
        if not self._running:
            return
        if self._flight_loop_id is not None:
            xp.destroyFlightLoop(self._flight_loop_id)
            self._flight_loop_id = None
        if self._scan_loop_id is not None:
            xp.destroyFlightLoop(self._scan_loop_id)
            self._scan_loop_id = None
        self._plans.clear()
        self._running = False
        xp.log("AIrport Mover: stopped")

    # -- Scan Redis for new plans ------------------------------------------

    def _scan(self, sinceLast, elapsedTime, counter, refCon):
        # 1) Honour any pending airborne spawn requests so the mover has an
        #    instance to drive before a move_cmd arrives.
        try:
            spawn_keys = self._r.keys(_SPAWN_REQUEST_PATTERN)
        except Exception as exc:
            xp.log(f"AIrport Mover: Redis spawn-scan error: {exc}")
            spawn_keys = []
        for key in spawn_keys:
            self._handle_spawn_request(key)

        # 2) Pick up move plans for already-spawned aircraft.
        try:
            keys = self._r.keys(_MOVE_CMD_PATTERN)
        except Exception as exc:
            xp.log(f"AIrport Mover: Redis scan error: {exc}")
            return 1.0

        seen_regs: set[str] = set()
        for key in keys:
            parts = key.split(":")
            if len(parts) < 3:
                continue
            reg = parts[1]
            # Skip the spawn_request namespace; same key prefix but different role.
            if reg == "spawn_request":
                continue
            seen_regs.add(reg)
            if reg not in self._spawner.registry:
                continue
            try:
                raw = self._r.get(key)
            except Exception:
                continue
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            self._ingest_plan(reg, payload)

        # Remove plans whose Redis key disappeared (e.g. TTL expired or cleared)
        for reg in list(self._plans.keys()):
            if reg not in seen_regs:
                self._finalise(reg, event="cancelled")

        return 1.0

    def _handle_spawn_request(self, key: str) -> None:
        """Spawn an aircraft from `aircraft:spawn_request:{reg}` (deletes the key)."""
        parts = key.split(":")
        if len(parts) < 3:
            return
        reg = parts[2]
        if reg in self._spawner.registry:
            try:
                self._r.delete(key)
            except Exception:
                pass
            return
        try:
            raw = self._r.get(key)
        except Exception:
            return
        if not raw:
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            try:
                self._r.delete(key)
            except Exception:
                pass
            return
        try:
            spawned = self._spawner.spawn_one(payload)
        except Exception as exc:
            xp.log(f"AIrport Mover: spawn_one failed for {reg}: {exc}")
            spawned = None
        if spawned:
            xp.log(f"AIrport Mover: dynamic spawn {spawned} (airborne={not payload.get('on_ground', True)})")
        try:
            self._r.delete(key)
        except Exception:
            pass

    def _ingest_plan(self, registration: str, payload: dict) -> None:
        plan_id = payload.get("plan_id") or f"legacy-{payload.get('started_at', time.time())}"
        existing = self._plans.get(registration)
        if existing and existing.plan_id == plan_id:
            return  # already running this plan

        legs = self._normalise_legs(payload)
        if not legs:
            return

        info = self._spawner.registry[registration]
        state = _PlanState(
            registration=registration,
            plan_id=plan_id,
            started_at=float(payload.get("started_at") or time.time()),
            delay_s=float(payload.get("delay_before_start_s") or 0.0),
            legs=legs,
            lat=info["latitude"],
            lon=info["longitude"],
            heading=info["true_hdg"],
            altitude_msl_ft=float(info.get("altitude_msl_ft", 0.0) or 0.0),
            on_ground=bool(info.get("on_ground", True)),
        )
        self._plans[registration] = state
        self._emit(registration, "plan_accepted", plan_id=plan_id)
        xp.log(
            f"AIrport Mover: accepted plan {plan_id} for {registration} "
            f"({len(legs)} leg(s), delay={state.delay_s:.1f}s)"
        )

    @staticmethod
    def _normalise_legs(payload: dict) -> list[dict]:
        """Accept both v2 multi-leg and legacy single-mode plans."""
        if "legs" in payload:
            return [leg for leg in payload["legs"] if leg.get("mode")]
        mode = payload.get("mode")
        if mode == "waypoints":
            return [
                {
                    "mode": "waypoints",
                    "waypoints": payload.get("waypoints") or [],
                    "speed_kts": float(payload.get("speed_kts", 8.0)),
                    "stop_at_end": True,
                }
            ]
        if mode == "straight":
            return [
                {
                    "mode": "straight",
                    "heading": float(payload.get("heading", 0.0)),
                    "speed_kts": float(payload.get("speed_kts", 5.0)),
                    "duration_s": float(payload.get("duration_s", 10.0)),
                }
            ]
        return []

    # -- Frame loop --------------------------------------------------------

    def _tick(self, sinceLast, elapsedTime, counter, refCon):
        dt = max(0.0, float(sinceLast))
        now = time.time()
        for reg in list(self._plans.keys()):
            plan = self._plans[reg]
            try:
                self._advance_plan(plan, dt, now)
            except Exception as exc:
                xp.log(f"AIrport Mover: advance error for {reg}: {exc}")
                self._finalise(reg, event="cancelled")
        return -1

    def _advance_plan(self, plan: _PlanState, dt: float, now: float) -> None:
        if plan.phase == "waiting":
            if now - plan.started_at >= plan.delay_s:
                self._enter_leg(plan)
            else:
                self._maybe_publish_state(plan, now, phase="parked", gs=0.0)
                return

        if plan.phase == "done":
            self._finalise(plan.registration, event="reached_end")
            return

        leg = plan.legs[plan.leg_index]
        mode = leg.get("mode")
        if mode == "pushback":
            self._advance_pushback(plan, leg, dt, now)
        elif mode in ("waypoints", "vacate", "taxi_in"):
            self._advance_waypoints(plan, leg, dt, now)
        elif mode == "straight":
            self._advance_straight(plan, leg, dt, now)
        elif mode == "approach":
            self._advance_approach(plan, leg, dt, now)
        elif mode == "landing_roll":
            self._advance_landing_roll(plan, leg, dt, now)
        else:
            xp.log(f"AIrport Mover: unknown leg mode {mode!r}; skipping")
            self._advance_leg(plan)

    def _enter_leg(self, plan: _PlanState) -> None:
        if plan.leg_index >= len(plan.legs):
            plan.phase = "done"
            return
        leg = plan.legs[plan.leg_index]
        mode = leg.get("mode")
        if mode == "pushback":
            plan.phase = "pushback"
            plan.pushback_start_lat = plan.lat
            plan.pushback_start_lon = plan.lon
            plan.pushback_start_heading = plan.heading
            plan.pushback_total_dist_m = float(leg.get("distance_m", 0.0))
            plan.pushback_traveled_m = 0.0
            plan.pushback_sub_phase = "reverse"
            self._emit(plan.registration, "pushback_started")
            self._emit(plan.registration, "pushback_reverse_started")
        elif mode == "waypoints":
            plan.phase = Phase.TAXI_OUT.value
            plan.wp_index = self._first_unreached_wp(plan, leg)
            # Telemetry only (issue #72): log the authorized taxiway
            # sequence for debrief correlation. The mover stays a dumb
            # waypoint executor and never re-derives routes.
            taxiway_sequence = leg.get("taxiway_sequence") or []
            if taxiway_sequence:
                xp.log(f"AIrport Mover: taxi leg for {plan.registration} authorized sequence: {taxiway_sequence}")
            self._emit(plan.registration, "taxi_started")
        elif mode == "straight":
            plan.phase = Phase.TAXI_OUT.value
            self._emit(plan.registration, "taxi_started")
        elif mode == "approach":
            plan.phase = Phase.APPROACH.value
            plan.on_ground = False
            plan.altitude_msl_ft = float(leg.get("initial_altitude_msl_ft", plan.altitude_msl_ft))
            plan.ias_kts = float(leg.get("ias_kts", 160.0))
            plan.vertical_speed_fpm = float(leg.get("vs_fpm", -800.0))
            self._emit(plan.registration, "approach_started")
        elif mode == "landing_roll":
            plan.phase = Phase.LANDING_ROLL.value
            plan.on_ground = True
            plan.altitude_msl_ft = float(leg.get("runway_elev_msl_ft", plan.altitude_msl_ft))
            plan.altitude_agl_ft = 0.0
            plan.vertical_speed_fpm = 0.0
            plan.ias_kts = float(leg.get("touchdown_ias_kts", plan.ias_kts if plan.ias_kts > 0 else 140.0))
            self._emit(plan.registration, "touchdown")
        elif mode == "vacate":
            plan.phase = Phase.VACATING.value
            plan.on_ground = True
            plan.wp_index = self._first_unreached_wp(plan, leg)
            self._emit(plan.registration, "vacate_started")
        elif mode == "taxi_in":
            plan.phase = Phase.TAXI_IN.value
            plan.on_ground = True
            plan.wp_index = self._first_unreached_wp(plan, leg)
            self._emit(plan.registration, "taxi_in_started")
        else:
            plan.phase = "done"

    def _advance_leg(self, plan: _PlanState) -> None:
        plan.leg_index += 1
        if plan.leg_index >= len(plan.legs):
            # Preserve the last working phase so _finalise can use it instead of "holding".
            if plan.phase not in ("waiting", "done"):
                plan.final_phase = plan.phase
            plan.phase = "done"
        else:
            self._enter_leg(plan)

    # -- Pushback leg -------------------------------------------------------

    def _advance_pushback(self, plan: _PlanState, leg: dict, dt: float, now: float) -> None:
        final_hdg = float(leg.get("final_heading_deg", plan.heading)) % 360.0

        if plan.pushback_sub_phase == "reverse":
            self._advance_pushback_reverse(plan, leg, dt, now)
            return

        if plan.pushback_sub_phase == "pivot":
            self._advance_pushback_pivot(plan, leg, dt, now, final_hdg)
            return

        # Unknown sub-phase → fall through to next leg defensively
        self._advance_leg(plan)

    def _advance_pushback_reverse(self, plan: _PlanState, leg: dict, dt: float, now: float) -> None:
        """Aircraft moves tail-first: advances along (heading + 180)°. Heading
        stays fixed at the original parked heading. This matches real ICAO
        pushback regardless of the stand's graph topology."""
        speed_kts = float(leg.get("speed_kts", 2.0))
        speed_mps = max(0.1, speed_kts * _KT_TO_MPS)
        step = speed_mps * dt

        back_bearing = (plan.pushback_start_heading + 180.0) % 360.0
        new_lat, new_lon = _advance(plan.lat, plan.lon, back_bearing, step)
        plan.lat, plan.lon = new_lat, new_lon
        plan.heading = plan.pushback_start_heading
        plan.pushback_traveled_m += step

        self._apply_position(plan, gs=speed_kts, phase="pushback")
        self._maybe_publish_state(plan, now, phase="pushback", gs=speed_kts)

        if plan.pushback_traveled_m >= plan.pushback_total_dist_m:
            plan.pushback_sub_phase = "pivot"
            self._emit(plan.registration, "pushback_pivot_started")

    def _advance_pushback_pivot(
        self,
        plan: _PlanState,
        leg: dict,
        dt: float,
        now: float,
        final_hdg: float,
    ) -> None:
        """Position fixed; rotate heading toward final_hdg at pivot_deg_per_s."""
        rate = float(leg.get("pivot_deg_per_s", 6.0))
        delta = _shortest_angle(plan.heading, final_hdg)
        if abs(delta) < 0.5:
            plan.heading = final_hdg
            self._apply_position(plan, gs=0.0, phase="pushback")
            self._advance_leg(plan)
            return

        step_deg = min(abs(delta), max(0.5, rate) * dt)
        if delta < 0:
            step_deg = -step_deg
        plan.heading = (plan.heading + step_deg) % 360.0

        self._apply_position(plan, gs=0.0, phase="pushback")
        self._maybe_publish_state(plan, now, phase="pushback", gs=0.0)

    # -- Waypoint taxi leg --------------------------------------------------

    def _advance_waypoints(self, plan: _PlanState, leg: dict, dt: float, now: float) -> None:
        waypoints = leg.get("waypoints") or []
        if plan.wp_index >= len(waypoints):
            if leg.get("stop_at_end", True):
                plan.ias_kts = 0.0
                # An arrival taxi_in that stops has arrived at the stand.
                if plan.phase == Phase.TAXI_IN.value:
                    plan.phase = Phase.PARKED.value
                self._apply_position(plan, gs=0.0, phase=plan.phase)
            self._advance_leg(plan)
            return

        speed_kts = float(leg.get("speed_kts", 8.0))
        speed_mps = max(0.1, speed_kts * _KT_TO_MPS)
        step = speed_mps * dt

        wp = waypoints[plan.wp_index]
        tgt_lat = float(wp["lat"])
        tgt_lon = float(wp["lon"])
        remaining = _haversine(plan.lat, plan.lon, tgt_lat, tgt_lon)

        if remaining <= max(step, _WAYPOINT_REACHED_M):
            plan.lat, plan.lon = tgt_lat, tgt_lon
            plan.wp_index += 1
            plan.ias_kts = speed_kts
            self._apply_position(plan, gs=speed_kts, phase=plan.phase)
            return

        bearing = _bearing(plan.lat, plan.lon, tgt_lat, tgt_lon)
        new_lat, new_lon = _advance(plan.lat, plan.lon, bearing, step)
        plan.lat, plan.lon = new_lat, new_lon
        plan.heading = bearing
        plan.ias_kts = speed_kts
        self._apply_position(plan, gs=speed_kts, phase=plan.phase)
        self._maybe_publish_state(plan, now, phase=plan.phase, gs=speed_kts)

    def _first_unreached_wp(self, plan: _PlanState, leg: dict) -> int:
        """Pick the first waypoint whose distance from the current position is
        above the reached-threshold. Avoids popping waypoints the pushback
        already passed through."""
        waypoints = leg.get("waypoints") or []
        for i, wp in enumerate(waypoints):
            d = _haversine(plan.lat, plan.lon, float(wp["lat"]), float(wp["lon"]))
            if d > _WAYPOINT_REACHED_M:
                return i
        return len(waypoints)

    # -- Straight leg (legacy test_move_straight) ---------------------------

    def _advance_straight(self, plan: _PlanState, leg: dict, dt: float, now: float) -> None:
        started = leg.setdefault("_t0", now)
        duration = float(leg.get("duration_s", 10.0))
        elapsed = now - started
        speed_kts = float(leg.get("speed_kts", 5.0))
        speed_mps = max(0.1, speed_kts * _KT_TO_MPS)
        heading = float(leg.get("heading", plan.heading))
        step = speed_mps * dt
        plan.lat, plan.lon = _advance(plan.lat, plan.lon, heading, step)
        plan.heading = heading
        self._apply_position(plan, gs=speed_kts, phase=Phase.TAXI_OUT.value)
        self._maybe_publish_state(plan, now, phase=Phase.TAXI_OUT.value, gs=speed_kts)
        if elapsed >= duration:
            self._advance_leg(plan)

    # -- Approach leg (fly toward threshold on localizer) ------------------

    def _advance_approach(self, plan: _PlanState, leg: dict, dt: float, now: float) -> None:
        """Fly the ILS final approach at constant IAS and descent rate.

        The aircraft flies along the runway heading (not toward the threshold
        point) so the bearing never reverses once it crosses the threshold.
        Transition to landing_roll happens when either:
          - altitude AGL drops to flare_agl_ft, OR
          - horizontal distance to the threshold is <= landing_transition_m.
        """
        from ...shared.services.geo import NM_TO_M

        target_lat = float(leg["target_lat"])
        target_lon = float(leg["target_lon"])
        runway_elev_msl_ft = float(leg.get("runway_elev_msl_ft", 0.0))
        flare_agl_ft = float(leg.get("flare_agl_ft", _FLARE_AGL_FT))
        request_dme_nm = leg.get("request_landing_at_nm")
        # landing_transition_m: max distance from threshold at which we land.
        # The distance check triggers landing_roll before the bearing can reverse.
        landing_transition_m = float(leg.get("landing_transition_m", 500.0))

        # Re-bear toward the threshold every frame: a great-circle nav that
        # follows the localizer exactly (no rhumb-line drift over 10+ NM).
        brg = _bearing(plan.lat, plan.lon, target_lat, target_lon)

        speed_mps = max(0.1, plan.ias_kts * _KT_TO_MPS)
        step = speed_mps * dt
        plan.heading = brg
        plan.lat, plan.lon = _advance(plan.lat, plan.lon, brg, step)

        plan.altitude_msl_ft += plan.vertical_speed_fpm * (dt / 60.0)
        plan.altitude_agl_ft = max(0.0, plan.altitude_msl_ft - runway_elev_msl_ft)

        dist_to_threshold_m = _haversine(plan.lat, plan.lon, target_lat, target_lon)

        if request_dme_nm is not None:
            dme_nm = dist_to_threshold_m / NM_TO_M
            if dme_nm <= float(request_dme_nm):
                self._emit(plan.registration, "request_landing", dme_nm=round(dme_nm, 2))

        self._apply_position(plan, gs=plan.ias_kts, phase=plan.phase)
        self._maybe_publish_state(plan, now, phase=plan.phase, gs=plan.ias_kts)

        if plan.altitude_agl_ft <= flare_agl_ft or dist_to_threshold_m <= landing_transition_m:
            self._emit(plan.registration, "flare_started")
            self._advance_leg(plan)

    # -- Landing roll leg (decelerate on runway) ---------------------------

    def _advance_landing_roll(self, plan: _PlanState, leg: dict, dt: float, now: float) -> None:
        """Decelerate along the runway centerline until below stop_kts."""
        decel_kts_s = float(leg.get("decel_kts_s", 4.0))
        rwy_hdg = float(leg.get("runway_hdg", plan.heading))
        stop_kts = float(leg.get("stop_kts", _LANDING_ROLL_STOP_KTS))

        plan.ias_kts = max(0.0, plan.ias_kts - decel_kts_s * dt)
        speed_mps = max(0.0, plan.ias_kts * _KT_TO_MPS)
        step = speed_mps * dt
        plan.heading = rwy_hdg
        if step > 0:
            plan.lat, plan.lon = _advance(plan.lat, plan.lon, rwy_hdg, step)

        plan.altitude_agl_ft = 0.0
        self._apply_position(plan, gs=plan.ias_kts, phase=plan.phase)
        self._maybe_publish_state(plan, now, phase=plan.phase, gs=plan.ias_kts)

        if plan.ias_kts <= stop_kts:
            self._emit(plan.registration, "rolling_out")
            self._advance_leg(plan)

    # -- X-Plane and state store -------------------------------------------

    def _apply_position(self, plan: _PlanState, *, gs: float, phase: str) -> None:
        info = self._spawner.registry.get(plan.registration)
        if not info or not info.get("instance"):
            return
        try:
            alt_m = plan.altitude_msl_ft * FT_TO_M if not plan.on_ground else 0.0
            x, y, z = xp.worldToLocal(lat=plan.lat, lon=plan.lon, alt=alt_m)
            if self._probe is not None:
                probe_info = xp.probeTerrainXYZ(self._probe, x, y, z)
                if probe_info.result == 0:
                    terrain_y = probe_info.locationY
                    if plan.on_ground:
                        # On ground: snap exactly to the local terrain surface.
                        y = terrain_y
                    else:
                        # Airborne: never let the .obj sink below local terrain.
                        # Keeps arrivals visible even when LEST's hilly approach
                        # cuts the geometric glideslope. 30 m above ground floor.
                        y = max(y, terrain_y + 30.0)
            pitch = -3.0 if phase == Phase.APPROACH.value else 0.0
            xp.instanceSetPosition(info["instance"], (x, y, z, pitch, plan.heading, 0.0), [])
            info["latitude"] = plan.lat
            info["longitude"] = plan.lon
            info["true_hdg"] = plan.heading
            info["altitude_msl_ft"] = plan.altitude_msl_ft
            info["on_ground"] = plan.on_ground
        except Exception as exc:
            xp.log(f"AIrport Mover: setPosition error for {plan.registration}: {exc}")

    def _maybe_publish_state(
        self,
        plan: _PlanState,
        now: float,
        *,
        phase: str,
        gs: float,
    ) -> None:
        if now - plan.last_state_publish < _STATE_FLUSH_INTERVAL_S:
            return
        plan.last_state_publish = now
        info = self._spawner.registry.get(plan.registration) or {}
        session = self._r.hgetall("session:current") or {}
        try:
            state = AircraftState(
                session_id=session.get("session_id", ""),
                registration=plan.registration,
                aircraft_type=info.get("aircraft_type", "UNKN"),
                callsign=info.get("callsign", plan.registration),
                latitude=plan.lat,
                longitude=plan.lon,
                altitude_msl=plan.altitude_msl_ft,
                altitude_agl=plan.altitude_agl_ft,
                heading=plan.heading,
                pitch=-3.0 if phase == Phase.APPROACH.value else 0.0,
                roll=0.0,
                ground_speed=gs,
                indicated_airspeed=plan.ias_kts,
                vertical_speed=plan.vertical_speed_fpm,
                on_ground=plan.on_ground,
                squawk=0,
                phase=phase,
            )
            self._store.update(state)
        except Exception as exc:
            xp.log(f"AIrport Mover: state publish error for {plan.registration}: {exc}")

    def _emit(self, registration: str, event: str, **extra) -> None:
        plan = self._plans.get(registration)
        if plan is not None:
            if event in plan.events_emitted:
                return
            plan.events_emitted.add(event)
        try:
            channel = f"aircraft:{registration}:move_events"
            payload = {"event": event, "ts": time.time(), **extra}
            self._r.publish(channel, json.dumps(payload))
        except Exception as exc:
            xp.log(f"AIrport Mover: emit error for {registration}: {exc}")

    def _finalise(self, registration: str, *, event: str) -> None:
        plan = self._plans.pop(registration, None)
        if plan is not None:
            if event == "reached_end":
                # Force final state publish using the last working phase so HMI
                # sees "parked" for arrivals (taxi_in done) or "holding" otherwise.
                final_phase = plan.final_phase or Phase.HOLDING.value
                plan.phase = final_phase
                plan.ias_kts = 0.0
                self._apply_position(plan, gs=0.0, phase=final_phase)
                self._maybe_publish_state(
                    plan,
                    time.time() + _STATE_FLUSH_INTERVAL_S,
                    phase=final_phase,
                    gs=0.0,
                )
            self._emit(registration, event)
        try:
            self._r.delete(f"aircraft:{registration}:move_cmd")
        except Exception:
            pass


_global_mover: Optional[AircraftMover] = None


def get_mover() -> Optional[AircraftMover]:
    """Return the session-scoped mover, or None if no session is running."""
    return _global_mover


def set_mover(mover: Optional[AircraftMover]) -> None:
    global _global_mover
    _global_mover = mover
