from google.adk.tools import ToolContext

from agent.tools.phase_advance import advance_phase


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
    return advance_phase(
        registration,
        frequency,
        tool_context,
        tool_name="advance_to_gnd",
        advance_state_key="advance_registration_gnd",
        dependency="GND",
    )
