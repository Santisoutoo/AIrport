from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Available ATC fine-tuned models exposed to the UI as a menu.
# Format: (hf_model_id, display_label, backend)
#   backend "faster-whisper" → uses CTranslate2 / faster-whisper library
#   backend "transformers"   → uses HuggingFace transformers pipeline (large-v3)


AVAILABLE_MODELS: list[dict] = [
    {
        "id": "jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper",
        "label": "Whisper Medium EN — ATC fine-tuned (faster-whisper)",
        "backend": "faster-whisper",
    },
    {
        "id": "jacktol/whisper-large-v3-finetuned-for-ATC",
        "label": "Whisper Large-v3 — ATC fine-tuned (transformers)",
        "backend": "transformers",
    },
    {
        "id": "jlvdoorn/whisper-tiny-atco2-asr",
        "label": "Whisper Tiny — ATC fine-tuned (jlvdoorn)",
        "backend": "transformers",
    },
    {
        "id": "jlvdoorn/whisper-medium-atco2-asr",
        "label": "Whisper Medium — ATC fine-tuned (jlvdoorn)",
        "backend": "transformers",
    },
    {
        "id": "jlvdoorn/whisper-large-v3-atco2-asr",
        "label": "Whisper Large-v3 — ATC fine-tuned (jlvdoorn)",
        "backend": "transformers",
    },
]

_MODEL_BACKENDS: dict[str, str] = {
    m["id"]: m["backend"] for m in AVAILABLE_MODELS}


def get_model_backend(model_id: str) -> Literal["faster-whisper", "transformers"]:
    """Return the inference backend for a given model ID."""
    return _MODEL_BACKENDS.get(model_id, "faster-whisper")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ASR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # HuggingFace ATC fine-tuned Whisper model (pick from AVAILABLE_MODELS)
    hf_model: str = "jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper"

    # Transcription
    whisper_language: str = "en"
    whisper_device: str = "cpu"          # "cpu" or "cuda"
    whisper_compute_type: str = "int8"   # "int8", "float16", "float32"
    whisper_beam_size: int = 5

    # Service
    request_timeout: float = 30.0
    port: int = 8000
    log_level: str = "info"
    workers: int = 1


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
