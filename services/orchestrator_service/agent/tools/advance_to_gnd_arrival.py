import logging
from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)


def advance_to_gnd_arrival(registration: str, frequency: str, tool_context: ToolContext) -> str:
    """
    Reverse handoff: an aircraft that has just LANDED and VACATED the runway
    is released from Tower back to Ground.

    Call this tool when the controller says "contact ground on {frequency}"
    AND the aircraft has previously been on Tower frequency for a LANDING
    (not a departure). Typical context: the pilot has already announced
    "runway vacated" or is in phase "vacating" / on the ground after touch-down.

    Use `advance_to_gnd` (NOT this tool) for the DEL → GND departure transition.

    Args:
        registration: The aircraft registration in canonical form (e.g. "EC-MIG").
        frequency: The ground frequency as spoken (e.g. "121.9").

    Returns:
        The standard ICAO pilot readback for a frequency change.
    """
    known = tool_context.state.get("known_aircraft", [])
    aircraft_data = next((a for a in known if a.get("registration") == registration), {})
    callsign = aircraft_data.get("callsign") or registration
    readback = f"{frequency}, {callsign}"
    tool_context.state["advance_registration_gnd_arrival"] = registration
    tool_context.state["reply"] = readback
    tool_context.state["dependency"] = "GND"
    tool_context.state["registration"] = registration
    logger.info("[ORCH] advance_to_gnd_arrival called for %s on %s", registration, frequency)
    return readback
