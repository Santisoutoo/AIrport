from google.adk.tools import ToolContext

from agent.tools.phase_advance import advance_phase


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
    return advance_phase(
        registration,
        frequency,
        tool_context,
        tool_name="advance_to_gnd_arrival",
        advance_state_key="advance_registration_gnd_arrival",
        dependency="GND",
    )
