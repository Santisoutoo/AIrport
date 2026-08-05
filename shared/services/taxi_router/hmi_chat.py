"""Publish pilot-side messages to the HMI controller chat.

The controller HMI subscribes to the `hmi:chat` Pub/Sub channel and renders
each payload as a chat line. This module is the only producer for now —
used when a pilot readback is unroutable ("unable, request alternative").
"""

import json
import time
from typing import Any, Optional

from . import config


def publish_pilot_message(
    redis_client: Any,
    *,
    callsign: str,
    registration: str,
    kind: str,
    text: str,
    session_id: Optional[str] = None,
) -> None:
    """Publish one chat line in the pilot's voice.

    `redis_client` is any redis.Redis-like object with `.publish()` /
    `.setex()`. We keep it as a parameter so the caller controls the
    connection pool.
    """
    payload = {
        "ts": time.time(),
        "session_id": session_id or "",
        "sender": "pilot",
        "callsign": callsign,
        "registration": registration,
        "kind": kind,
        "text": text,
    }
    redis_client.publish(config.HMI_CHAT_CHANNEL, json.dumps(payload))
    redis_client.rpush("tts:queue", json.dumps({"text": text}))

    key = config.LAST_ERROR_KEY.format(registration=registration)
    redis_client.setex(key, config.LAST_ERROR_TTL_S, json.dumps(payload))


def format_readback_rejected(callsign: str, reason: str) -> str:
    """Text template for a 'unable' message in the pilot's voice."""
    return f"{callsign}, unable, {reason}. Request alternative."
