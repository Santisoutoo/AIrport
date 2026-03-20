import os
from enum import Enum

from dotenv import load_dotenv

load_dotenv()


class AgentMode(str, Enum):
    OFFLINE = "offline"
    CLOUD = "cloud"


class Config:
    AGENT_MODE: AgentMode = AgentMode(os.getenv("AGENT_MODE", "offline"))

    # Offline — Ollama via LiteLLM
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    # Cloud — Vertex AI via LiteLLM
    VERTEX_MODEL: str = os.getenv("VERTEX_MODEL", "gemini-3-flash-preview")
    VERTEX_PROJECT: str = os.getenv("VERTEX_PROJECT", "")
    VERTEX_LOCATION: str = os.getenv("VERTEX_LOCATION", "us-central1")

    # Service settings
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8011"))

    # A2A URLs of sibling agents (set these in Cloud Run env vars)
    DEL_AGENT_URL: str = os.getenv("DEL_AGENT_URL", "http://localhost:8010")
    TWR_AGENT_URL: str = os.getenv("TWR_AGENT_URL", "http://localhost:8012")

    def get_litellm_model(self) -> str:
        if self.AGENT_MODE == AgentMode.CLOUD:
            return f"vertex_ai/{self.VERTEX_MODEL}"
        return f"ollama/{self.OLLAMA_MODEL}"


config = Config()
