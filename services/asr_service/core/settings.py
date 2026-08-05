# Deprecated — use core.config instead.
from .config import Settings, get_settings

# Legacy constants kept for backward compatibility
import os

REQUEST_TIMEOUT: float = float(os.getenv("ASR_REQUEST_TIMEOUT", "30"))
WHISPER_LANGUAGE: str = os.getenv("ASR_WHISPER_LANGUAGE", "en")
