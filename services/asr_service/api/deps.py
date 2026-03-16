import os
from functools import lru_cache

import redis as redis_lib


@lru_cache(maxsize=1)
def get_redis() -> redis_lib.Redis:
    """Cached Redis client (one connection pool per process)."""
    return redis_lib.from_url(
        os.getenv("REDIS_URL", "redis://redis:6379"),
        decode_responses=True,
    )
