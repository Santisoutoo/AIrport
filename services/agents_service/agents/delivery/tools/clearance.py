def make_issue_clearance(context: dict):
    """
    Factory that returns an `issue_clearance` tool bound to the given
    per-request context dict. After the agent calls the tool, the dict will
    contain a "clearance_data" key with all structured clearance fields.
    """

    def issue_clearance(
        aircraft_registration: str,
        squawk: int,
        initial_altitude: int,
        instrumental_departure: str,
        runway_in_use: str,
        altimeter: float,
        destination_icao: str,
        clearance_text: str,
    ) -> str:
        """
        Record the IFR departure clearance issued to an aircraft.

        Args:
            aircraft_registration: Aircraft callsign in canonical form (e.g. "EC-MIG").
            squawk:                 Assigned transponder code (4-digit octal, e.g. 2347).
            initial_altitude:       Initial cleared altitude in feet (e.g. 5000).
            instrumental_departure: SID name (e.g. "DVOR1F") or "DIRECT" if none assigned.
            runway_in_use:          Departure runway designator (e.g. "32L").
            altimeter:              Current QNH in hPa (e.g. 1013.0).
            destination_icao:       Destination airport ICAO code (e.g. "LEMD").
            clearance_text:         Full verbatim clearance text as spoken to the pilot.

        Returns:
            Acknowledgment string confirming the clearance was recorded.
        """
        context["clearance_data"] = {
            "aircraft_registration": aircraft_registration,
            "squawk": squawk,
            "initial_altitude": initial_altitude,
            "instrumental_departure": instrumental_departure,
            "runway_in_use": runway_in_use,
            "altimeter": altimeter,
            "destination_icao": destination_icao,
            "clearance_text": clearance_text,
        }
        return "Clearance recorded."

    return issue_clearance
