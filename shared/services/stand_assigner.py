
class StandAssigner:
    """Assigns available stands to flight plans."""

    def assign(self, flight_plans: list, stands: list) -> list:
        """
        Assign a free and compatible stand to each flight plan.
        """
        assignments = []
        available = []
        for s in stands:
            if not s["occupied"]:
                available.append(s)

        for fp in flight_plans:
            aircraft_type = fp["aircraft_type"]
            stand = self._find_compatible(aircraft_type, available)

            if stand is None and available:
                stand = available[0]

            if stand is None:
                continue

            available.remove(stand)

            assignments.append({
                "aircraft_registration": fp["aircraft_registration"],
                "aircraft_type": aircraft_type,
                "stand_id": stand["stand_id"],
                "latitude": stand["latitude"],
                "longitude": stand["longitude"],
                "true_hdg": stand["true_hdg"],
            })

        return assignments

    def _find_compatible(self, aircraft_type: str, available: list):
        """Find first available stand that allows this aircraft type."""
        for stand in available:
            allowed = stand.get("allowed_aircraft_types", "")
            allowed_list = allowed.split("|")
            if aircraft_type in allowed_list:
                return stand
        return None
