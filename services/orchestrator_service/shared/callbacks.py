import logging

from google.adk.agents.callback_context import CallbackContext

logger = logging.getLogger(__name__)


def log_before(callback_context: CallbackContext) -> None:
    aircraft = callback_context.state.get("known_aircraft", [])
    logger.info(
        "[ORCH] ▶ starting | session=%s | transcription=%r | known_aircraft=%d",
        callback_context.state.get("session_id"),
        callback_context.state.get("raw_transcription", "")[:100],
        len(aircraft),
    )
    for a in aircraft:
        logger.debug("[ORCH]   aircraft: %s dep=%s source=%s", a.get("registration"), a.get("dependency"), a.get("source"))


def log_after(callback_context: CallbackContext) -> None:
    logger.info(
        "[ORCH] ■ done | dep=%s | reg=%s | clearance_data=%s",
        callback_context.state.get("dependency"),
        callback_context.state.get("registration"),
        callback_context.state.get("clearance_data"),
    )
