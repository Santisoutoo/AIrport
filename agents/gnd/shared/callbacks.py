import logging

from google.adk.agents.callback_context import CallbackContext

logger = logging.getLogger(__name__)


def log_before(callback_context: CallbackContext) -> None:
    logger.info(
        "[GND] agent starting | session=%s | transcription=%r",
        callback_context.state.get("session_id"),
        str(callback_context.state.get("raw_transcription", ""))[:100],
    )


def log_after(callback_context: CallbackContext) -> None:
    taxi_data = callback_context.state.get("taxi_data")
    instruction_text = callback_context.state.get("instruction_text", "")
    logger.info(
        "[GND] agent done | instruction_text: %r | taxi_data: %s",
        instruction_text[:80] if instruction_text else "",
        taxi_data,
    )
