def make_issue_clearance(context: dict):
    """
    Factory that returns an issue_clearance tool that stores clearance data
    in the shared context dict instead of posting to the orchestrator.
    The orchestrator will read this data from the response and persist it locally.
    """
    def issue_clearance(
        registration: str,
        squawk: int,
        initial_altitude: int,
        instrumental_departure: str,
        runway_in_use: str,
        altimeter: float,
        destination_icao: str,
        clearance_text: str,
    ) -> dict:
        """
        Record the IFR delivery clearance for an aircraft.

        Stores the clearance details so the orchestrator can persist them to the
        database. Sets the aircraft dependency to DEL (cleared, not yet with Ground).

        Returns a confirmation dict with status and registration.
        """
        context["clearance_data"] = {
            "aircraft_registration": registration,
            "squawk": squawk,
            "initial_altitude": initial_altitude,
            "instrumental_departure": instrumental_departure,
            "runway_in_use": runway_in_use,
            "altimeter": altimeter,
            "destination_icao": destination_icao,
            "clearance_text": clearance_text,
        }
        return {"status": "ok", "registration": registration, "dependency": "DEL"}

    return issue_clearance
