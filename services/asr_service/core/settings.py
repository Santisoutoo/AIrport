# Deprecated — use core.config instead.
import os

# Re-exported on purpose: this module is a backward-compatibility shim, so the
# names must stay importable from here even though it does not use them.
from .config import Settings, get_settings  # noqa: F401

# Legacy constants kept for backward compatibility
REQUEST_TIMEOUT: float = float(os.getenv("ASR_REQUEST_TIMEOUT", "30"))
WHISPER_LANGUAGE: str = os.getenv("ASR_WHISPER_LANGUAGE", "en")
