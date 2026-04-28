"""Per-session capture log kept in Redis for the debrief generator.

Three lists indexed by session_id, TTL 2h so they self-clean:
  - session:{sid}:transcripts   — what the controller said (ASR output).
  - session:{sid}:agent_replies — what each pilot agent replied.
  - session:{sid}:events        — move_events + hmi:chat rejections.

Every append is fire-and-forget with best-effort semantics; if Redis is
unavailable we log and continue — capture is non-critical path.
"""

import json
import logging
import os
import time
from typing import Any, Optional

import redis as redis_lib

logger = logging.getLogger(__name__)

_TTL_SECONDS = 7200  # 2 hours

_TRANSCRIPTS_KEY = "session:{sid}:transcripts"
_AGENT_REPLIES_KEY = "session:{sid}:agent_replies"
_EVENTS_KEY = "session:{sid}:events"
_SESSION_REQUEST_KEY = "airport:session_request"


def _redis_client() -> redis_lib.Redis:
    host = os.getenv("REDIS_HOST", "redis")
    port = int(os.getenv("REDIS_PORT", 6379))
    db = int(os.getenv("REDIS_DB", 0))
    return redis_lib.Redis(host=host, port=port, db=db, decode_responses=True)


_r: Optional[redis_lib.Redis] = None


def _client() -> redis_lib.Redis:
    global _r
    if _r is None:
        _r = _redis_client()
    return _r


def _push(key: str, payload: dict) -> None:
    try:
        c = _client()
        pipe = c.pipeline()
        pipe.lpush(key, json.dumps(payload))
        pipe.expire(key, _TTL_SECONDS)
        pipe.execute()
    except Exception as exc:
        logger.warning("[session_log] failed to push to %s: %s", key, exc)


def append_transcript(session_id: str, text: str) -> None:
    if not session_id or not text:
        return
    _push(_TRANSCRIPTS_KEY.format(sid=session_id), {
        "ts": time.time(),
        "text": text,
    })


def append_agent_reply(
    session_id: str,
    dep: str,
    registration: Optional[str],
    callsign: Optional[str],
    reply: str,
    taxi_data: Optional[dict] = None,
) -> None:
    if not session_id:
        return
    _push(_AGENT_REPLIES_KEY.format(sid=session_id), {
        "ts": time.time(),
        "dep": dep,
        "registration": registration,
        "callsign": callsign,
        "reply": reply,
        "taxi_data": taxi_data,
    })


def append_event(
    session_id: str,
    registration: Optional[str],
    event: str,
    extra: Optional[dict] = None,
) -> None:
    if not session_id or not event:
        return
    _push(_EVENTS_KEY.format(sid=session_id), {
        "ts": time.time(),
        "registration": registration,
        "event": event,
        "extra": extra or {},
    })


def get_active_session_id() -> Optional[str]:
    try:
        c = _client()
        sid = c.hget(_SESSION_REQUEST_KEY, "session_id")
        return sid if sid else None
    except Exception as exc:
        logger.warning("[session_log] failed to read active session: %s", exc)
        return None


def _lrange(key: str) -> list[dict]:
    try:
        c = _client()
        raw = c.lrange(key, 0, -1) or []
        out: list[dict] = []
        for item in raw:
            try:
                out.append(json.loads(item))
            except json.JSONDecodeError:
                continue
        # Items were LPUSHed so newest is first; the debrief wants chronological
        out.reverse()
        return out
    except Exception as exc:
        logger.warning("[session_log] failed to lrange %s: %s", key, exc)
        return []


def get_transcripts(session_id: str) -> list[dict]:
    return _lrange(_TRANSCRIPTS_KEY.format(sid=session_id))


def get_agent_replies(session_id: str) -> list[dict]:
    return _lrange(_AGENT_REPLIES_KEY.format(sid=session_id))


def get_events(session_id: str) -> list[dict]:
    return _lrange(_EVENTS_KEY.format(sid=session_id))
