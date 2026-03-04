from .deps import get_redis
from .models import AsrConfig, DEFAULTS, REDIS_KEY


def load() -> dict[str, str]:
    """Load ASR config from Redis, merging with defaults."""
    data = get_redis().hgetall(REDIS_KEY)
    return {**DEFAULTS, **data}


def save(cfg: AsrConfig) -> None:
    """Persist ASR config to Redis."""
    get_redis().hset(REDIS_KEY, mapping=cfg.model_dump())
