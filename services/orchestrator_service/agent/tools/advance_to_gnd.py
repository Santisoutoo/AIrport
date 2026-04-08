import logging
from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)


def advance_to_gnd(registration: str, frequency: str, tool_context: ToolContext) -> str:
    """
    Advance the aircraft from DEL to GND phase when the controller releases
    it to ground with a phrase like "contact ground on {frequency}".

    Call this tool when the controller says "contact ground", "contact GND",
    or any equivalent ICAO release phrase for a DEL-phase aircraft.

    Args:
        registration: The aircraft registration in canonical form (e.g. "EC-MIG").
        frequency: The ground frequency as spoken (e.g. "121.9").

    Returns:
        The standard ICAO pilot readback for a frequency change.
    """
    readback = f"{frequency}, {registration}"
    tool_context.state["advance_registration_gnd"] = registration
    tool_context.state["reply"] = readback
    tool_context.state["dependency"] = "GND"
    tool_context.state["registration"] = registration
    logger.info("[ORCH] advance_to_gnd called for %s on %s", registration, frequency)
    return readback
