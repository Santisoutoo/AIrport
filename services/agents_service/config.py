import os
from enum import Enum


class AgentMode(str, Enum):
    OFFLINE = "offline"
    CLOUD = "cloud"


class Config:
    AGENT_MODE: AgentMode = AgentMode(os.getenv("AGENT_MODE", "offline"))

    # Offline — Ollama via LiteLLM
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1")
    OLLAMA_BASE_URL: str = os.getenv(
        "OLLAMA_BASE_URL", "http://localhost:11434")

    # Cloud — Vertex AI via LiteLLM
    VERTEX_MODEL: str = os.getenv("VERTEX_MODEL", "gemini-2.0-flash")
    VERTEX_PROJECT: str = os.getenv("VERTEX_PROJECT", "")
    VERTEX_LOCATION: str = os.getenv("VERTEX_LOCATION", "us-central1")

    # Service settings
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8002"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info")

    def get_litellm_model(self) -> str:
        """Returns the LiteLLM model string for the active mode."""
        if self.AGENT_MODE == AgentMode.CLOUD:
            return f"vertex_ai/{self.VERTEX_MODEL}"
        return f"ollama/{self.OLLAMA_MODEL}"


config = Config()
