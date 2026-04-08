import logging
from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)


def confirm_readback(registration: str, tool_context: ToolContext) -> str:
    """
    Confirm that the pilot's readback was correct and advance the aircraft
    from DEL to GND phase.

    Call this tool when the controller says "readback correct", "correct",
    or any equivalent ICAO confirmation phrase for a DEL-phase aircraft.
    Do NOT call it if the controller says "negative" or asks for a re-read.

    Args:
        registration: The aircraft registration in canonical form (e.g. "EC-MIG").

    Returns:
        A short confirmation string (not spoken — used internally).
    """
    tool_context.state["advance_registration"] = registration
    tool_context.state["reply"] = ""          # controller has already spoken
    tool_context.state["dependency"] = "GND"
    tool_context.state["registration"] = registration
    logger.info("[ORCH] confirm_readback called for %s", registration)
    return f"Readback confirmed. {registration} advancing to GND."
