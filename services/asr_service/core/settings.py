import os


# LLM post-correction
LLM_MODEL: str = os.getenv("ASR_LLM_MODEL", "gpt-5-mini")
LLM_MAX_TOKENS: int = int(os.getenv("ASR_LLM_MAX_TOKENS", "200"))
LLM_TEMPERATURE: float = float(os.getenv("ASR_LLM_TEMPERATURE", "0"))

# Whisper
WHISPER_LANGUAGE: str = os.getenv("ASR_WHISPER_LANGUAGE", "en")
REQUEST_TIMEOUT: float = float(os.getenv("ASR_REQUEST_TIMEOUT", "30"))
