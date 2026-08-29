"""Builds and dispatches an arrival's flight-leg plan to Redis.

Three legs are emitted:
  1. approach      — fly from spawn point on the localizer to the threshold,
                     descending at 3°. The mover emits a `request_landing`
                     event at request_landing_at_nm (4 NM).
  2. landing_roll  — decelerate along the runway centerline until stop_kts.
  3. vacate        — taxi (single waypoint) from the runway to the E3 turnoff.

The actual movement is performed by the X-Plane plugin's AircraftMover
once it picks up `aircraft:{reg}:move_cmd` from Redis. The plugin also
needs to spawn the .obj airborne — that's published separately to
`aircraft:spawn_request:{reg}`.
"""

import json
import logging
import os
import time

import httpx
import redis

from shared.services.geo import project_on_localizer

from .runway_config import RunwayConfig

logger = logging.getLogger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
_HMI_URL = os.getenv("HMI_SERVICE_URL", "http://controller_hmi_service:8000")
_ORCH_URL = os.getenv("ORCHESTRATOR_SERVICE_URL", "http://orchestrator_service:8006")

SPAWN_DISTANCE_NM = float(os.getenv("ARRIVAL_SPAWN_DISTANCE_NM", "10.0"))
# 5000 ft AGL at 10 NM keeps the aircraft above LEST surrounding terrain
# (hills up to ~2000 ft MSL within 10 NM of the field). With -1333 fpm at
# 160 kt the descent reaches 0 AGL exactly at the threshold (~4.7° slope).
SPAWN_ALTITUDE_AGL_FT = float(os.getenv("ARRIVAL_SPAWN_ALT_AGL_FT", "5000.0"))
APPROACH_IAS_KTS = float(os.getenv("ARRIVAL_IAS_KTS", "160.0"))
APPROACH_VS_FPM = float(os.getenv("ARRIVAL_VS_FPM", "-1333.0"))
REQUEST_LANDING_AT_NM = float(os.getenv("ARRIVAL_REQUEST_AT_NM", "4.0"))
LANDING_ROLL_DECEL_KTS_S = float(os.getenv("ARRIVAL_DECEL_KTS_S", "4.0"))
LANDING_ROLL_STOP_KTS = float(os.getenv("ARRIVAL_STOP_KTS", "20.0"))
VACATE_TAXI_KTS = float(os.getenv("ARRIVAL_VACATE_KTS", "15.0"))


def _redis_client() -> redis.Redis:
    return redis.from_url(_REDIS_URL, decode_responses=True)


def _spawn_point(runway: RunwayConfig,
                 spawn_distance_nm: float) -> tuple[float, float, float]:
    """Return (lat, lon, altitude MSL ft) of the spawn point on the localizer.

    Altitude scales proportionally with distance so every staggered slot sits
    on the same glideslope.
    """
    spawn_lat, spawn_lon = project_on_localizer(
        runway.threshold_lat, runway.threshold_lon,
        runway.heading_deg, spawn_distance_nm,
    )
    agl = SPAWN_ALTITUDE_AGL_FT * (spawn_distance_nm / SPAWN_DISTANCE_NM)
    return spawn_lat, spawn_lon, agl + runway.elevation_ft


def _build_spawn_request(reg: str, callsign: str, aircraft_type: str,
                         runway: RunwayConfig, spawn_lat: float, spawn_lon: float,
                         spawn_alt_msl: float) -> dict:
    """Payload the X-Plane plugin needs to create the .obj airborne."""
    return {
        "aircraft_registration": reg,
        "callsign": callsign,
        "aircraft_type": aircraft_type,
        "latitude": spawn_lat,
        "longitude": spawn_lon,
        "altitude_msl_ft": spawn_alt_msl,
        "true_hdg": runway.heading_deg,
        "on_ground": False,
        "ts": time.time(),
    }


def _build_move_cmd(plan_id: str, runway: RunwayConfig, spawn_alt_msl: float) -> dict:
    """Three-leg move plan (approach -> landing_roll -> vacate) for the mover."""
    approach_leg = {
        "mode": "approach",
        "target_lat": runway.threshold_lat,
        "target_lon": runway.threshold_lon,
        "runway_hdg": runway.heading_deg,
        "runway_elev_msl_ft": runway.elevation_ft,
        "initial_altitude_msl_ft": spawn_alt_msl,
        "ias_kts": APPROACH_IAS_KTS,
        "vs_fpm": APPROACH_VS_FPM,
        "request_landing_at_nm": REQUEST_LANDING_AT_NM,
        "flare_agl_ft": 50.0,
        "landing_transition_m": 500.0,
    }
    landing_roll_leg = {
        "mode": "landing_roll",
        "runway_hdg": runway.heading_deg,
        "touchdown_ias_kts": 140.0,
        "decel_kts_s": LANDING_ROLL_DECEL_KTS_S,
        "stop_kts": LANDING_ROLL_STOP_KTS,
    }
    vacate_leg = {
        "mode": "vacate",
        "waypoints": [
            # 1. point on the runway centerline, abeam the exit — the
            #    aircraft rolls straight here before turning off.
            {"lat": runway.vacate_abeam_lat, "lon": runway.vacate_abeam_lon},
            # 2. the actual taxiway exit (E3) — sharp turn off the runway.
            {"lat": runway.vacate_exit_lat,  "lon": runway.vacate_exit_lon},
        ],
        "speed_kts": VACATE_TAXI_KTS,
        "stop_at_end": True,
    }
    return {
        "version": 2,
        "plan_id": plan_id,
        "started_at": time.time(),
        "delay_before_start_s": 0.0,
        "legs": [approach_leg, landing_roll_leg, vacate_leg],
    }


def _publish_to_redis(reg: str, spawn_request: dict, move_cmd: dict) -> None:
    r = _redis_client()
    r.set(f"aircraft:spawn_request:{reg}", json.dumps(spawn_request))
    r.set(f"aircraft:{reg}:move_cmd", json.dumps(move_cmd))


def _register_hmi_strip(plan: dict, reg: str, callsign: str, aircraft_type: str) -> None:
    """Register a virtual strip in the HMI so it appears in the ARRIVALS column.

    Best effort: the arrival is already published to Redis, so a failure here
    only costs the controller the visual strip.
    """
    try:
        with httpx.Client(timeout=3.0) as client:
            client.post(
                f"{_HMI_URL}/api/v1/hmi/strips/arrival",
                json={
                    "aircraft_registration": reg,
                    "callsign": callsign,
                    "aircraft_type": aircraft_type,
                    "departure_ICAO": plan.get("departure_ICAO", "ZZZZ"),
                    "destination_ICAO": "LEST",
                },
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not register arrival strip in HMI for %s: %s", reg, exc)


def _register_in_orchestrator(reg: str, callsign: str, aircraft_type: str,
                              runway: RunwayConfig) -> None:
    """Register the arrival in the orchestrator's DB so dependency='APP'.

    This is what makes the orchestrator correctly route the reverse handoff
    (advance_to_gnd_arrival) when the controller later says "contact ground".
    Best effort, same rationale as the HMI strip.
    """
    try:
        with httpx.Client(timeout=3.0) as client:
            client.post(
                f"{_ORCH_URL}/api/v1/orchestrator/arrivals/register",
                json={
                    "aircraft_registration": reg,
                    "callsign": callsign,
                    "aircraft_type": aircraft_type,
                    "destination_icao": runway.icao,
                    "runway_in_use": runway.runway_id,
                },
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not register arrival %s in orchestrator: %s", reg, exc)


def dispatch_arrival(plan: dict, runway: RunwayConfig,
                     spawn_distance_nm: float = SPAWN_DISTANCE_NM) -> dict:
    """Publish the spawn request and the multi-leg move plan to Redis.

    `spawn_distance_nm` allows callers to stagger multiple simultaneous
    arrivals along the localizer. Altitude scales proportionally with
    distance to preserve the 3° glideslope for all slots.

    Returns the dispatch metadata (spawn point, plan_id) for logging.
    """
    reg = plan["aircraft_registration"]
    callsign = plan.get("callsign") or reg
    aircraft_type = plan["aircraft_type"]

    spawn_lat, spawn_lon, spawn_alt_msl = _spawn_point(runway, spawn_distance_nm)
    plan_id = f"arr-{reg}-{int(time.time())}"

    _publish_to_redis(
        reg,
        _build_spawn_request(reg, callsign, aircraft_type, runway,
                             spawn_lat, spawn_lon, spawn_alt_msl),
        _build_move_cmd(plan_id, runway, spawn_alt_msl),
    )

    _register_hmi_strip(plan, reg, callsign, aircraft_type)
    _register_in_orchestrator(reg, callsign, aircraft_type, runway)

    logger.info(
        "Dispatched arrival %s (%s, %s): spawn at (%.5f, %.5f) %.0f ft, plan_id=%s",
        reg, callsign, aircraft_type, spawn_lat, spawn_lon, spawn_alt_msl, plan_id,
    )

    return {
        "registration": reg,
        "callsign": callsign,
        "plan_id": plan_id,
        "spawn_lat": spawn_lat,
        "spawn_lon": spawn_lon,
        "spawn_alt_msl_ft": spawn_alt_msl,
        "runway": runway.runway_id,
    }
