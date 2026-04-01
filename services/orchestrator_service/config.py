import os


class Config:
    # Upstream services
    FLIGHT_PLAN_SERVICE_URL: str = os.getenv(
        "FLIGHT_PLAN_SERVICE_URL", "http://flight_plan_service:8003/api/v1/flight-plan"
    )
    WEATHER_SERVICE_URL: str = os.getenv(
        "WEATHER_SERVICE_URL", "http://weather_service:8004/api/v1/weather"
    )

    # PostgreSQL
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "postgres")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "airport")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "airport_user")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "password")

    # Redis (position tracking — read only from here)
    REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))

    # Agent Cloud Run URLs
    DEL_AGENT_URL: str = os.getenv("DEL_AGENT_URL", "http://del_service:8080")
    GND_AGENT_URL: str = os.getenv("GND_AGENT_URL", "http://gnd_service:8080")
    TWR_AGENT_URL: str = os.getenv("TWR_AGENT_URL", "http://twr_service:8080")

    # LLM — Vertex AI via LiteLLM
    VERTEX_PROJECT: str = os.getenv("VERTEX_PROJECT", "")
    VERTEX_LOCATION: str = os.getenv("VERTEX_LOCATION", "global")
    VERTEX_MODEL: str = os.getenv("VERTEX_MODEL", "gemini-3.0-flash-preview")

    @property
    def LITELLM_MODEL(self) -> str:
        return f"vertex_ai/{self.VERTEX_MODEL}"

    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8006"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info")


config = Config()
