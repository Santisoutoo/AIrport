"""Fetches flight plans tagged as arrivals from flight_plan_service.

An arrival is a flight plan whose `destination_ICAO` matches the active
airport (LEST). If no such plans exist in the DB, a built-in synthetic
pool is used so the simulator works out of the box.
"""

import itertools
import logging
import os

import httpx
import redis

logger = logging.getLogger(__name__)

_FLIGHT_PLAN_URL = os.getenv(
    "FLIGHT_PLAN_SERVICE_URL",
    "http://flight_plan_service:8000/api/v1/flight-plan",
)
_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
_ASSIGNED_SET = "arrivals:assigned"

# Built-in pool used when no DB plans with destination=LEST exist.
_SYNTHETIC_POOL = [
    {"aircraft_registration": "EC-ARR1", "callsign": "IBE3001", "aircraft_type": "A320", "departure_ICAO": "LEMD", "destination_ICAO": "LEST"},
    {"aircraft_registration": "EC-ARR2", "callsign": "VLG4502", "aircraft_type": "A321", "departure_ICAO": "LEBL", "destination_ICAO": "LEST"},
    {"aircraft_registration": "EI-ARR3", "callsign": "RYR7810", "aircraft_type": "B738", "departure_ICAO": "EGSS", "destination_ICAO": "LEST"},
    {"aircraft_registration": "EC-ARR4", "callsign": "IBE3045", "aircraft_type": "A320", "departure_ICAO": "LPPT", "destination_ICAO": "LEST"},
    {"aircraft_registration": "EC-ARR5", "callsign": "VLG4610", "aircraft_type": "A321", "departure_ICAO": "LEVC", "destination_ICAO": "LEST"},
    {"aircraft_registration": "EI-ARR6", "callsign": "RYR5521", "aircraft_type": "B738", "departure_ICAO": "EIDW", "destination_ICAO": "LEST"},
]
_synthetic_cycle = itertools.cycle(_SYNTHETIC_POOL)


def _redis_client() -> redis.Redis:
    return redis.from_url(_REDIS_URL, decode_responses=True)


async def fetch_pending_arrival(destination_icao: str) -> dict | None:
    """Return one un-dispatched arrival flight plan, or None if exhausted.

    Priority: DB plans with destination_ICAO == airport. Fallback: synthetic pool.
    Plans already dispatched are tracked in Redis set `arrivals:assigned`.
    """
    r = _redis_client()
    assigned = r.smembers(_ASSIGNED_SET) or set()

    # 1. Try DB plans first.
    db_plan = await _fetch_from_db(destination_icao, assigned)
    if db_plan is not None:
        return db_plan

    # 2. Fallback: synthetic pool (cycles indefinitely).
    for _ in range(len(_SYNTHETIC_POOL)):
        candidate = next(_synthetic_cycle)
        reg = candidate["aircraft_registration"]
        if reg not in assigned:
            logger.info("plan_catalog: using synthetic arrival %s (%s)", reg, candidate["callsign"])
            return candidate

    # All synthetic slots also assigned — reset and restart.
    logger.info("plan_catalog: all synthetic slots assigned, resetting pool.")
    r.delete(_ASSIGNED_SET)
    return next(_synthetic_cycle)


async def _fetch_from_db(destination_icao: str, assigned: set) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{_FLIGHT_PLAN_URL}/plans")
            resp.raise_for_status()
            plans = resp.json() or []
    except httpx.HTTPError as exc:
        logger.warning("plan_catalog: flight_plan_service unreachable: %s", exc)
        return None

    for plan in plans:
        if plan.get("destination_ICAO", "").upper() != destination_icao.upper():
            continue
        reg = plan["aircraft_registration"]
        if reg not in assigned:
            return plan
    return None


def mark_assigned(registration: str) -> None:
    _redis_client().sadd(_ASSIGNED_SET, registration)


def reset_assignments() -> None:
    """Clear the assigned set (used on /arrivals/stop)."""
    _redis_client().delete(_ASSIGNED_SET)
    global _synthetic_cycle
    _synthetic_cycle = itertools.cycle(_SYNTHETIC_POOL)
