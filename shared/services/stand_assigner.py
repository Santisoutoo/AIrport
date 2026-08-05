import random
from typing import Optional, cast

# ICAO width code ordering for size comparison
_WIDTH_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5}

# Map ICAO aircraft type codes to apt.dat categories and width codes
_AIRCRAFT_CLASSIFICATION = {
    "C172": {"apt_category": "props", "icao_width_code": "A"},
    "PA28": {"apt_category": "props", "icao_width_code": "A"},
    "E190": {"apt_category": "jets", "icao_width_code": "C"},
    "B737": {"apt_category": "jets", "icao_width_code": "C"},
    "B738": {"apt_category": "jets", "icao_width_code": "C"},
    "A320": {"apt_category": "jets", "icao_width_code": "C"},
    "A321": {"apt_category": "jets", "icao_width_code": "C"},
}

_AIRLINE_OPERATION_TYPES = {"airline", "cargo"}
_GA_CATEGORIES = {"props"}


class StandAssigner:
    """Assigns available stands to flight plans."""

    def assign(self, flight_plans: list, stands: list) -> list:
        """
        Assign a free and compatible stand to each flight plan.
        """
        assignments = []
        available = [s for s in stands if not s["occupied"]]
        random.shuffle(available)

        for fp in flight_plans:
            aircraft_type = fp["aircraft_type"]
            stand = self._find_compatible(aircraft_type, available)

            if stand is None:
                continue

            available.remove(stand)

            assignments.append(
                {
                    "aircraft_registration": fp["aircraft_registration"],
                    "aircraft_type": aircraft_type,
                    "callsign": fp.get("callsign", fp["aircraft_registration"]),
                    "stand_id": stand["stand_id"],
                    "latitude": stand["latitude"],
                    "longitude": stand["longitude"],
                    "true_hdg": stand["true_hdg"],
                }
            )

        return assignments

    def _find_compatible(self, aircraft_type: str, available: list) -> Optional[dict]:
        """Find first available stand compatible with this aircraft type."""
        classification = _AIRCRAFT_CLASSIFICATION.get(aircraft_type)
        if classification is None:
            return None

        apt_category = classification["apt_category"]
        acft_width = classification["icao_width_code"]
        is_ga = apt_category in _GA_CATEGORIES

        for stand in available:
            # Check 1: aircraft category must be in allowed_aircraft_types
            allowed = stand.get("allowed_aircraft_types", "")
            if apt_category not in allowed.split("|"):
                continue

            # Check 2: ICAO width — aircraft must fit in stand
            stand_width = stand.get("icao_width_code", "")
            if stand_width and acft_width:
                if _WIDTH_ORDER.get(acft_width, 0) > _WIDTH_ORDER.get(stand_width, 5):
                    continue

            # Check 3: GA aircraft must not use airline/cargo gates
            operation_type = stand.get("operation_type", "")
            if is_ga and operation_type in _AIRLINE_OPERATION_TYPES:
                continue

            # Check 4: airline aircraft must use gate stands only (terminal-integrated)
            if not is_ga and stand.get("stand_type", "") != "gate":
                continue

            return cast(dict, stand)

        return None
