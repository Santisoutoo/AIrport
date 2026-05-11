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

SPAWN_DISTANCE_NM = float(os.getenv("ARRIVAL_SPAWN_DISTANCE_NM", "10.0"))
SPAWN_ALTITUDE_AGL_FT = float(os.getenv("ARRIVAL_SPAWN_ALT_AGL_FT", "3000.0"))
APPROACH_IAS_KTS = float(os.getenv("ARRIVAL_IAS_KTS", "160.0"))
APPROACH_VS_FPM = float(os.getenv("ARRIVAL_VS_FPM", "-800.0"))
REQUEST_LANDING_AT_NM = float(os.getenv("ARRIVAL_REQUEST_AT_NM", "4.0"))
LANDING_ROLL_DECEL_KTS_S = float(os.getenv("ARRIVAL_DECEL_KTS_S", "4.0"))
LANDING_ROLL_STOP_KTS = float(os.getenv("ARRIVAL_STOP_KTS", "20.0"))
VACATE_TAXI_KTS = float(os.getenv("ARRIVAL_VACATE_KTS", "15.0"))


def _redis_client() -> redis.Redis:
    return redis.from_url(_REDIS_URL, decode_responses=True)


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

    spawn_lat, spawn_lon = project_on_localizer(
        runway.threshold_lat, runway.threshold_lon,
        runway.heading_deg, spawn_distance_nm,
    )
    # Scale AGL proportionally so every slot sits on the same 3° glideslope.
    agl = SPAWN_ALTITUDE_AGL_FT * (spawn_distance_nm / SPAWN_DISTANCE_NM)
    spawn_alt_msl = agl + runway.elevation_ft

    spawn_request = {
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

    plan_id = f"arr-{reg}-{int(time.time())}"
    move_cmd = {
        "version": 2,
        "plan_id": plan_id,
        "started_at": time.time(),
        "delay_before_start_s": 0.0,
        "legs": [
            {
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
            },
            {
                "mode": "landing_roll",
                "runway_hdg": runway.heading_deg,
                "touchdown_ias_kts": 140.0,
                "decel_kts_s": LANDING_ROLL_DECEL_KTS_S,
                "stop_kts": LANDING_ROLL_STOP_KTS,
            },
            {
                "mode": "vacate",
                "waypoints": [
                    {"lat": runway.vacate_exit_lat, "lon": runway.vacate_exit_lon},
                ],
                "speed_kts": VACATE_TAXI_KTS,
                "stop_at_end": True,
            },
        ],
    }

    r = _redis_client()
    r.set(f"aircraft:spawn_request:{reg}", json.dumps(spawn_request))
    r.set(f"aircraft:{reg}:move_cmd", json.dumps(move_cmd))

    # Register a virtual strip in the HMI so it appears in ARRIVALS column.
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
