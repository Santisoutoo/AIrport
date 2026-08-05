from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Optional


class Intent(Enum):
    CLEARANCE = "clearance"
    STARTUP = "startup"
    PUSHBACK = "pushback"
    TAXI = "taxi"
    HOLD_SHORT = "hold_short"
    GIVE_WAY = "give_way"
    LINE_UP = "line_up"
    TAKEOFF = "takeoff"
    LANDING = "landing"
    CLIMB = "climb"
    DESCEND = "descend"
    TURN = "turn"
    CONTACT = "contact"
    REPORT = "report"
    CONDITIONAL = "conditional"
    UNKNOWN = "unknown"


@dataclass
class ParsedCommand:
    intent: Intent

    # Identificación
    callsign: Optional[str] = None

    # Clearance (DEL)
    destination: Optional[str] = None
    sid: Optional[str] = None
    runway: Optional[str] = None
    initial_climb: Optional[int] = None
    qnh: Optional[str] = None
    squawk: Optional[str] = None

    # Startup/Pushback
    pushback_direction: Optional[str] = None

    # Taxi
    holding_point: Optional[str] = None
    taxiway_route: Optional[List[str]] = None

    # Give way / Hold short
    traffic_type: Optional[str] = None
    reference_point: Optional[str] = None

    # Takeoff/Landing
    wind_direction: Optional[int] = None
    wind_speed: Optional[int] = None

    # Conditional clearance
    conditional_traffic: Optional[str] = None
    behind_traffic: Optional[str] = None

    # Post-departure
    after_departure_turn: Optional[str] = None
    after_departure_heading: Optional[str] = None

    # En-route
    flight_level: Optional[int] = None
    heading: Optional[int] = None
    speed: Optional[int] = None
    frequency: Optional[str] = None

    # Metadata
    confidence: float = 0.0
    raw_transcription: str = ""
    language: str = "en"

    def to_dict(self) -> dict[str, Any]:
        """Convierte a diccionario para JSON/MQTT"""
        result: dict[str, Any] = {
            "intent": self.intent.value,
            "callsign": self.callsign,
            "confidence": self.confidence,
            "raw_transcription": self.raw_transcription,
            "language": self.language,
        }

        optional_fields = [
            "destination",
            "sid",
            "runway",
            "initial_climb",
            "qnh",
            "squawk",
            "pushback_direction",
            "holding_point",
            "taxiway_route",
            "traffic_type",
            "reference_point",
            "wind_direction",
            "wind_speed",
            "conditional_traffic",
            "behind_traffic",
            "after_departure_turn",
            "after_departure_heading",
            "flight_level",
            "heading",
            "speed",
            "frequency",
        ]

        for field in optional_fields:
            value = getattr(self, field, None)
            if value is not None:
                result[field] = value

        return result
