import json
import os
import threading
from typing import Any, Optional, cast

import redis
from influxdb_client import InfluxDBClient

from ..models.aircraft_state import AircraftState


def _load_env() -> None:
    """Load .env file into os.environ"""
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    try:
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())
    except FileNotFoundError:
        pass


_load_env()


_AIRCRAFT_PREFIX = "aircraft:state"
_ACTIVE_SET_KEY = "aircraft:active_set"
_UPDATES_CHANNEL = "aircraft:updates"
_STATE_TTL_SECONDS = 3600


# See the note in airport_data_store: redis-py's stubs type the sync client
# as `Awaitable[T] | T`, so it stays `Any` here too.
def _get_redis_client() -> Any:
    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", 6379))
    db = int(os.getenv("REDIS_DB", 0))
    return redis.Redis(host=host, port=port, db=db, decode_responses=True)


class AircraftStateStore:
    """Manages aircraft state in Redis and InfluxDB."""

    def __init__(self, redis_client: Any = None, influx_client: Any = None) -> None:
        self._r = redis_client or _get_redis_client()
        self._influx = influx_client
        self._influx_write_api = None

        # Buffer for batching InfluxDB writes
        self._influx_buffer: list[Any] = []
        self._influx_buffer_lock = threading.Lock()
        self._influx_flush_size = 20  # flush every N points

        if self._influx is not None:
            self._init_influx()

    def _init_influx(self) -> None:
        """Initialise the InfluxDB write API."""
        self._influx_write_api = self._influx.write_api()

    def connect_influx(self) -> None:
        """Connect to InfluxDB. Called when the session starts."""
        try:
            url = os.getenv("INFLUXDB_URL", "http://localhost:8087")
            token = os.getenv("INFLUXDB_TOKEN", "")
            org = os.getenv("INFLUXDB_ORG", "airport")
            self._influx = InfluxDBClient(url=url, token=token, org=org)
            self._influx_write_api = self._influx.write_api()
        except Exception as e:
            print(f"AIrport: Could not connect to InfluxDB: {e}")
            self._influx = None
            self._influx_write_api = None

    # Write

    def update(self, state: AircraftState) -> None:
        """
        Write an aircraft state snapshot.

        1. Update the Redis hash for this aircraft (current state).
        2. Add the aircraft to the active set.
        3. Publish the update via Pub/Sub.
        4. Buffer the point for InfluxDB and flush when the buffer is full.
        """
        key = f"{_AIRCRAFT_PREFIX}:{state.registration}"
        state_dict = state.to_dict()

        pipe = self._r.pipeline()
        pipe.hset(key, mapping=state_dict)
        pipe.expire(key, _STATE_TTL_SECONDS)
        pipe.sadd(_ACTIVE_SET_KEY, state.registration)
        pipe.publish(_UPDATES_CHANNEL, json.dumps(state_dict))
        pipe.execute()

        # Buffer for InfluxDB
        if self._influx_write_api is not None:
            with self._influx_buffer_lock:
                self._influx_buffer.append(state.to_influx_point())
                if len(self._influx_buffer) >= self._influx_flush_size:
                    self._flush_influx()

    def _flush_influx(self) -> None:
        """Write buffered points to InfluxDB. Must hold _influx_buffer_lock."""
        if not self._influx_buffer or self._influx_write_api is None:
            return
        try:
            bucket = os.getenv("INFLUXDB_BUCKET", "airport")
            org = os.getenv("INFLUXDB_ORG", "airport")
            self._influx_write_api.write(
                bucket=bucket,
                org=org,
                record=self._influx_buffer,
            )
        except Exception as e:
            print(f"AIrport: InfluxDB write error: {e}")
        finally:
            self._influx_buffer.clear()

    def flush(self) -> None:
        """Force-flush any remaining InfluxDB buffer (call on session end)."""
        with self._influx_buffer_lock:
            self._flush_influx()

    # Read (real-time from Redis)

    def get_state(self, registration: str) -> Optional[dict]:
        """Return the current state hash for a single aircraft."""
        key = f"{_AIRCRAFT_PREFIX}:{registration}"
        data = self._r.hgetall(key)
        return data if data else None

    def get_all_states(self) -> list[dict]:
        """Return current state for every active aircraft."""
        registrations = self._r.smembers(_ACTIVE_SET_KEY)
        states = []
        for reg in registrations:
            state = self.get_state(reg)
            if state:
                states.append(state)
        return states

    def get_active_registrations(self) -> set[str]:
        """Return the set of currently tracked aircraft registrations."""
        return cast(set, self._r.smembers(_ACTIVE_SET_KEY))

    # Read (historical from InfluxDB)

    def query_replay(
        self,
        session_id: str,
        registration: Optional[str] = None,
        start: Optional[str] = None,
        stop: Optional[str] = None,
    ) -> list[dict]:
        """
        Query InfluxDB for historical aircraft state data.

        Args:
            session_id: The training session UUID.
            registration: Optional filter for a single aircraft.
            start: ISO 8601 start time (default: -1h).
            stop: ISO 8601 stop time (default: now()).

        Returns:
            List of state records ordered by time.
        """
        if self._influx is None:
            return []

        bucket = os.getenv("INFLUXDB_BUCKET", "airport")
        start_clause = f", start: {start}" if start else ", start: -1h"
        stop_clause = f", stop: {stop}" if stop else ""
        reg_filter = ""
        if registration:
            reg_filter = f'|> filter(fn: (r) => r["registration"] == "{registration}")'

        query = f'''
            from(bucket: "{bucket}")
                |> range({start_clause}{stop_clause})
                |> filter(fn: (r) => r["_measurement"] == "aircraft_state")
                |> filter(fn: (r) => r["session_id"] == "{session_id}")
                {reg_filter}
                |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
                |> sort(columns: ["_time"])
        '''

        try:
            query_api = self._influx.query_api()
            tables = query_api.query(query)
            results = []
            for table in tables:
                for record in table.records:
                    results.append(record.values)
            return results
        except Exception as e:
            print(f"AIrport: InfluxDB query error: {e}")
            return []

    # Cleanup

    def remove_aircraft(self, registration: str) -> None:
        """Remove an aircraft from active tracking."""
        self._r.delete(f"{_AIRCRAFT_PREFIX}:{registration}")
        self._r.srem(_ACTIVE_SET_KEY, registration)

    def clear_all(self) -> None:
        """Remove all aircraft state data from Redis."""
        registrations = self._r.smembers(_ACTIVE_SET_KEY)
        pipe = self._r.pipeline()
        for reg in registrations:
            pipe.delete(f"{_AIRCRAFT_PREFIX}:{reg}")
        pipe.delete(_ACTIVE_SET_KEY)
        pipe.execute()

    def close(self) -> None:
        """Flush buffers and close connections."""
        self.flush()
        if self._influx is not None:
            self._influx.close()
