import logging
from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)


def advance_to_twr(registration: str, frequency: str, tool_context: ToolContext) -> str:
    """
    Advance the aircraft from GND to TWR phase when the controller releases
    it to tower with a phrase like "contact tower on {frequency}".

    Call this tool when the controller says "contact tower", "contact TWR",
    "frequency change approved", or any equivalent ICAO release phrase for
    a GND-phase aircraft.

    Args:
        registration: The aircraft registration in canonical form (e.g. "EC-MIG").
        frequency: The tower frequency as spoken (e.g. "118.1").

    Returns:
        The standard ICAO pilot readback for a frequency change.
    """
    known = tool_context.state.get("known_aircraft", [])
    aircraft_data = next((a for a in known if a.get("registration") == registration), {})
    callsign = aircraft_data.get("callsign") or registration
    readback = f"{frequency}, {callsign}"
    tool_context.state["advance_registration_twr"] = registration
    tool_context.state["reply"] = readback
    tool_context.state["dependency"] = "TWR"
    tool_context.state["registration"] = registration
    logger.info("[ORCH] advance_to_twr called for %s on %s", registration, frequency)
    return readback
