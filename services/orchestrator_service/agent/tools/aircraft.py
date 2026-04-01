"""
Tool: get_known_aircraft

Returns the list of aircraft the orchestrator currently knows about, including
their current ATC dependency (DEL / GND / TWR).

Sources (merged and deduplicated):
  1. aircraft_clearances table (PostgreSQL) — authoritative dependency field
  2. flight_plan_service GET /plans       — aircraft that have filed a flight plan
  3. Redis aircraft:active_set            — aircraft with active position tracking
"""
import logging
import os
from typing import Any

import httpx
import redis as redis_lib
from sqlalchemy.orm import Session

from config import config
from db.models import AircraftClearance

logger = logging.getLogger(__name__)


def _get_redis() -> redis_lib.Redis:
    return redis_lib.Redis(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        db=0,
        decode_responses=True,
    )


def make_get_known_aircraft(db: Session):
    """
    Factory that returns a `get_known_aircraft` tool function bound to the
    given SQLAlchemy session.  This allows per-request DB access inside a
    module-level ADK Agent.
    """

    def get_known_aircraft() -> list[dict[str, Any]]:
        """
        Return a list of known aircraft with their current ATC dependency.

        Each item has:
          - registration (str): ICAO registration, e.g. "EC-MIG"
          - dependency (str):   current controller — "DEL", "GND", or "TWR"
          - source (str):       where the record came from
        """
        # registration → {dependency, source}
        aircraft: dict[str, dict[str, str]] = {}

        # 1. PostgreSQL — most authoritative
        try:
            rows = db.query(
                AircraftClearance.aircraft_registration,
                AircraftClearance.dependency,
            ).all()
            for reg, dep in rows:
                aircraft[reg] = {"dependency": dep, "source": "db"}
        except Exception as exc:
            logger.warning("DB query failed in get_known_aircraft: %s", exc)

        # 2. Flight plan service — aircraft that have filed but may not be cleared yet
        try:
            resp = httpx.get(f"{config.FLIGHT_PLAN_SERVICE_URL}/plans", timeout=5)
            if resp.status_code == 200:
                for plan in resp.json():
                    reg = plan.get("aircraft_registration")
                    if reg and reg not in aircraft:
                        aircraft[reg] = {"dependency": "DEL", "source": "flight_plan"}
        except Exception as exc:
            logger.warning("flight_plan_service unavailable: %s", exc)

        # 3. Redis active set — aircraft with live position data
        try:
            r = _get_redis()
            for reg in r.smembers("aircraft:active_set"):
                if reg not in aircraft:
                    aircraft[reg] = {"dependency": "DEL", "source": "redis"}
        except Exception as exc:
            logger.warning("Redis unavailable: %s", exc)

        return [
            {"registration": reg, **info}
            for reg, info in aircraft.items()
        ]

    return get_known_aircraft
