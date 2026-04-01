def make_get_flight_plan(flight_plan: dict | None):
    """
    Factory that returns a get_flight_plan tool pre-loaded with data
    fetched by the orchestrator before calling this agent.
    """
    def get_flight_plan(registration: str) -> dict:
        """
        Retrieve the flight plan for an aircraft by its registration (callsign).

        Returns a dict with fields: aircraft_registration, destination_icao, route,
        cruising_altitude, cruising_speed, flight_rules, aircraft_type, departure_icao,
        instrumental_departure, transponder, equipment.
        Returns {"error": "..."} if not available.
        """
        if flight_plan:
            return flight_plan
        return {"error": f"No flight plan available for {registration}"}

    return get_flight_plan
