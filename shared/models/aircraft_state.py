from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class AircraftState:
    """Snapshot of an aircraft's state at a point in time."""

    # Metadata (tags in InfluxDB)
    session_id: str
    registration: str
    aircraft_type: str
    callsign: str

    # Position & orientation
    latitude: float        # degrees
    longitude: float       # degrees
    altitude_msl: float    # feet
    altitude_agl: float    # feet
    heading: float         # degrees
    pitch: float           # degrees
    roll: float            # degrees

    # Speeds
    ground_speed: float       # knots
    indicated_airspeed: float # knots
    vertical_speed: float     # feet per minute

    # State
    on_ground: bool
    squawk: int
    phase: str

    timestamp: Optional[str] = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    # Serialisation helpers

    def to_dict(self) -> dict:
        """
        Convert to dict
        """

        d = asdict(self)

        # Redis does not accept boolean values and int values
        d["on_ground"] = "1" if self.on_ground else "0"
        d["squawk"] = str(self.squawk)
        for k, v in d.items():
            if isinstance(v, float):
                d[k] = str(round(v, 6))

        return d

    def to_influx_point(self) -> dict:
        """
        Return a dict ready for the InfluxDB write API.
        """
        return {
            "measurement": "aircraft_state",
            "tags": {
                "session_id": self.session_id,
                "registration": self.registration,
                "aircraft_type": self.aircraft_type,
                "callsign": self.callsign,
            },
            "fields": {
                "latitude": self.latitude,
                "longitude": self.longitude,
                "altitude_msl": self.altitude_msl,
                "altitude_agl": self.altitude_agl,
                "heading": self.heading,
                "pitch": self.pitch,
                "roll": self.roll,
                "ground_speed": self.ground_speed,
                "indicated_airspeed": self.indicated_airspeed,
                "vertical_speed": self.vertical_speed,
                "on_ground": self.on_ground,
                "squawk": self.squawk,
                "phase": self.phase,
            },
            "time": self.timestamp,
        }
