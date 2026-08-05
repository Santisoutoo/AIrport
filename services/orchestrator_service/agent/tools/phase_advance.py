"""Shared implementation behind the three frequency-change "advance" tools.

`advance_to_gnd`, `advance_to_twr` and `advance_to_gnd_arrival` differ only in
the controller phase they hand the aircraft to, the state key `runner.py` reads
afterwards, and the docstring the LLM sees. Everything else — the callsign
lookup, the ICAO readback format and the four state writes — is identical, and
lives here.

The tools themselves stay in their own modules as thin wrappers so the ADK keeps
seeing three distinct names, signatures and descriptions; see #52.
"""

import logging

from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)


def advance_phase(
    registration: str,
    frequency: str,
    tool_context: ToolContext,
    *,
    tool_name: str,
    advance_state_key: str,
    dependency: str,
) -> str:
    """Emit the frequency-change readback and flag the handoff in state.

    Args:
        registration:      Aircraft registration in canonical form ("EC-MIG").
        frequency:         The new frequency as spoken ("121.9").
        tool_context:      ADK tool context; ``state["known_aircraft"]`` is read
                           and four keys are written back.
        tool_name:         Name of the calling tool, for the log line only.
        advance_state_key: The single state key `runner.py` inspects to know
                           which handoff happened. Exactly one of
                           ``advance_registration_gnd``,
                           ``advance_registration_twr`` or
                           ``advance_registration_gnd_arrival`` — never more,
                           or the runner would double-dispatch.
        dependency:        Controller phase the aircraft moves to.

    Returns:
        The standard ICAO pilot readback for a frequency change.
    """
    known = tool_context.state.get("known_aircraft", [])
    aircraft_data = next((a for a in known if a.get("registration") == registration), {})
    callsign = aircraft_data.get("callsign") or registration
    readback = f"{frequency}, {callsign}"
    tool_context.state[advance_state_key] = registration
    tool_context.state["reply"] = readback
    tool_context.state["dependency"] = dependency
    tool_context.state["registration"] = registration
    logger.info("[ORCH] %s called for %s on %s", tool_name, registration, frequency)
    return readback
