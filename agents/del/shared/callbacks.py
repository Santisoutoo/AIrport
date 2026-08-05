import logging

from google.adk.agents.callback_context import CallbackContext

logger = logging.getLogger(__name__)


def log_before(callback_context: CallbackContext) -> None:
    logger.info(
        "[DEL] ▶ agent starting | session=%s | transcription=%r",
        callback_context.state.get("session_id"),
        str(callback_context.state.get("raw_transcription", ""))[:100],
    )


def log_after(callback_context: CallbackContext) -> None:
    clearance_data = callback_context.state.get("clearance_data")
    clearance_text = callback_context.state.get("clearance_text", "")
    logger.info(
        "[DEL] ■ agent done | clearance_text: %r | clearance_data: %s",
        clearance_text[:80] if clearance_text else "",
        clearance_data,
    )
