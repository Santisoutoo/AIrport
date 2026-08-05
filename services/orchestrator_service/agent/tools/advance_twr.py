from google.adk.tools import ToolContext

from agent.tools.phase_advance import advance_phase


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
    return advance_phase(
        registration,
        frequency,
        tool_context,
        tool_name="advance_to_twr",
        advance_state_key="advance_registration_twr",
        dependency="TWR",
    )
