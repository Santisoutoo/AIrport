import os
from enum import Enum
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class AgentMode(str, Enum):
    OFFLINE = "offline"
    CLOUD = "cloud"


class Config:
    # LLM post-processing mode
    AGENT_MODE: AgentMode = AgentMode(os.getenv("AGENT_MODE", "offline"))

    # Offline — Ollama via LiteLLM
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    # Cloud — Vertex AI via LiteLLM
    VERTEX_MODEL: str = os.getenv("VERTEX_MODEL", "gemini-3-flash-preview")
    VERTEX_PROJECT: str = os.getenv("VERTEX_PROJECT", "")
    VERTEX_LOCATION: str = os.getenv("VERTEX_LOCATION", "us-central1")

    # Whisper settings
    HF_MODEL: str = os.getenv(
        "ASR_HF_MODEL",
        "jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper",
    )
    WHISPER_LANGUAGE: str = os.getenv("ASR_WHISPER_LANGUAGE", "en")
    WHISPER_DEVICE: str = os.getenv("ASR_WHISPER_DEVICE", "cpu")
    WHISPER_COMPUTE_TYPE: str = os.getenv("ASR_WHISPER_COMPUTE_TYPE", "int8")
    WHISPER_BEAM_SIZE: int = int(os.getenv("ASR_WHISPER_BEAM_SIZE", "5"))

    # Service settings
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8013"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info")

    def get_litellm_model(self) -> str:
        if self.AGENT_MODE == AgentMode.CLOUD:
            return f"vertex_ai/{self.VERTEX_MODEL}"
        return f"ollama/{self.OLLAMA_MODEL}"


@lru_cache(maxsize=1)
def get_config() -> Config:
    return Config()
