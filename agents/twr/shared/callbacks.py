import logging
from google.adk.agents.callback_context import CallbackContext

logger = logging.getLogger(__name__)


def log_before(callback_context: CallbackContext) -> None:
    logger.info(
        "[TWR] agent starting | session=%s | transcription=%r",
        callback_context.state.get("session_id"),
        str(callback_context.state.get("raw_transcription", ""))[:100],
    )


def log_after(callback_context: CallbackContext) -> None:
    reply_data = callback_context.state.get("reply_data")
    reply_text = callback_context.state.get("reply_text", "")
    logger.info(
        "[TWR] agent done | reply_text: %r | reply_data: %s",
        reply_text[:80] if reply_text else "",
        reply_data,
    )
