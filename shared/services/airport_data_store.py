"""
Store and retrieve parsed airport data from Redis.

Used by both the X-Plane plugin and the microservices to share
airport data (nodes, edges, stands, runways, etc.) for the
currently loaded airport.
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional
import redis


_PREFIX = "airport:current"


def _get_redis_client():
    """Create a Redis client from environment variables."""
    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", 6379))
    db = int(os.getenv("REDIS_DB", 0))
    return redis.Redis(host=host, port=port, db=db, decode_responses=True)


class AirportDataStore:
    """Read/write parsed airport data in Redis."""

    def __init__(self, client=None):
        self._r = client or _get_redis_client()

    def store(self, icao: str, parsed_data: dict) -> None:
        """
        Store parsed airport data in Redis.

        Args:
            icao: ICAO code of the airport (e.g. "LEBL").
            parsed_data: Dict with keys matching the parser output:
                nodes, edges, stands, runways, traffic_patterns, airport_info.
                Each value is a list of dicts (dataclass.__dict__).
        """
        pipe = self._r.pipeline()

        self._delete_current(pipe)

        pipe.set(f"{_PREFIX}:icao", icao.upper())
        pipe.set(f"{_PREFIX}:timestamp", datetime.now(timezone.utc).isoformat())

        for key, value in parsed_data.items():
            pipe.set(f"{_PREFIX}:{key}", json.dumps(value))

        pipe.execute()

    def load(self) -> Optional[dict]:
        """
        Load the full airport dataset from Redis.

        Returns:
            Dict with icao, timestamp, and all parsed sections,
            or None if no airport data is stored.
        """
        icao = self._r.get(f"{_PREFIX}:icao")
        if icao is None:
            return None

        timestamp = self._r.get(f"{_PREFIX}:timestamp")

        keys = [
            "nodes", "edges", "stands",
            "runways", "traffic_patterns", "airport_info",
        ]

        data = {"icao": icao, "timestamp": timestamp}
        for key in keys:
            raw = self._r.get(f"{_PREFIX}:{key}")
            data[key] = json.loads(raw) if raw else []

        return data

    def get_icao(self) -> Optional[str]:
        """Return the ICAO code of the currently stored airport."""
        return self._r.get(f"{_PREFIX}:icao")

    def clear(self) -> None:
        """Remove all current airport data from Redis."""
        self._delete_current(self._r)

    # Stand occupancy
    _OCCUPANCY_KEY = f"{_PREFIX}:stand_occupancy"

    def init_stand_occupancy(self, stands: list) -> None:
        """Initialize all stands as unoccupied ('0')."""
        if not stands:
            return None

        # Borrar ocupación anterior
        self._r.delete(self._OCCUPANCY_KEY)

        # Marcar cada stand como libre
        for stand in stands:
            stand_id = stand["stand_id"]
            self._r.hset(self._OCCUPANCY_KEY, stand_id, "0")

    def set_stand_occupied(self, stand_id: str, occupied: bool) -> None:
        """Mark a stand as occupied or free."""
        self._r.hset(self._OCCUPANCY_KEY, stand_id, "1" if occupied else "0")

    def is_stand_occupied(self, stand_id: str) -> bool:
        """Return True if the stand is currently occupied."""
        return self._r.hget(self._OCCUPANCY_KEY, stand_id) == "1"

    def get_stands_with_occupancy(self) -> list:
        """Return stands list with an 'occupied' bool field added to each."""
        raw = self._r.get(f"{_PREFIX}:stands")
        if raw:
            stands = json.loads(raw)
        else:
            stands = []

        occupancy = self._r.hgetall(self._OCCUPANCY_KEY)

        # Añadir campo 'occupied' a cada stand
        for stand in stands:
            stand_id = stand["stand_id"]
            value = occupancy.get(stand_id, "0")
            if value == "1":
                stand["occupied"] = True
            else:
                stand["occupied"] = False

        return stands

    def _delete_current(self, pipe) -> None:
        """Delete all keys under the current airport prefix."""
        keys = self._r.keys(f"{_PREFIX}:*")
        if keys:
            pipe.delete(*keys)
