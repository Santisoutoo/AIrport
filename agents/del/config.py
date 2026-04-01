import os
from enum import Enum


class AgentMode(str, Enum):
    CLOUD = "cloud"
    OFFLINE = "offline"


class Config:
    AGENT_MODE: AgentMode = AgentMode(os.getenv("AGENT_MODE", "cloud"))

    # LiteLLM → Vertex AI
    VERTEX_MODEL: str = os.getenv("VERTEX_MODEL", "gemini-3.0-flash-preview")
    VERTEX_PROJECT: str = os.getenv("VERTEX_PROJECT", "")
    VERTEX_LOCATION: str = os.getenv("VERTEX_LOCATION", "global")

    # Orchestrator
    ORCHESTRATOR_URL: str = os.getenv(
        "ORCHESTRATOR_URL", "http://orchestrator_service:8006")

    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8080"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info")

    def get_litellm_model(self) -> str:
        return f"vertex_ai/{self.VERTEX_MODEL}"


config = Config()
