import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8009"))

    # Cloud Run service URLs (set in env for production)
    TRANSCRIPTION_URL: str = os.getenv("TRANSCRIPTION_URL", "http://localhost:8013")
    DEL_AGENT_URL: str = os.getenv("DEL_AGENT_URL", "http://localhost:8010")
    GND_AGENT_URL: str = os.getenv("GND_AGENT_URL", "http://localhost:8011")
    TWR_AGENT_URL: str = os.getenv("TWR_AGENT_URL", "http://localhost:8012")


config = Config()
