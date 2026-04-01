def make_get_atis(atis: dict | None):
    """
    Factory that returns a get_atis tool pre-loaded with data
    fetched by the orchestrator before calling this agent.
    """
    def get_atis(icao: str) -> dict:
        """
        Retrieve the latest ATIS for an airport by its ICAO code.

        Returns a dict with fields: atis_letter, qnh_hpa, departure_runway,
        arrival_runway, wind_direction, wind_speed, visibility_m, temperature_c,
        transition_level, raw_metar, atis_text.
        Returns {"error": "..."} if not available.
        """
        if atis:
            return atis
        return {"error": f"No ATIS available for {icao}"}

    return get_atis
