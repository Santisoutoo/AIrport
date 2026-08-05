"""Background subscriber that captures move_events + hmi:chat into Redis
lists tagged by the active session_id, so the debrief can reconstruct
the timeline.

Runs as an asyncio.Task started in the FastAPI lifespan; shuts down
cleanly on app shutdown.
"""

import asyncio
import json
import logging
import os
from typing import Optional

import redis.asyncio as redis_async
from session_log import append_event, get_active_session_id

logger = logging.getLogger(__name__)

_MOVE_EVENTS_PATTERN = "aircraft:*:move_events"
_CHAT_CHANNEL = "hmi:chat"


class EventsSubscriber:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="events_subscriber")
        logger.info("[events_subscriber] started")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
            self._task = None
        logger.info("[events_subscriber] stopped")

    async def _run(self) -> None:
        url = os.getenv("REDIS_URL") or f"redis://{os.getenv('REDIS_HOST', 'redis')}:{os.getenv('REDIS_PORT', '6379')}"
        while not self._stop.is_set():
            try:
                client = redis_async.from_url(url, decode_responses=True)
                pubsub = client.pubsub()
                await pubsub.psubscribe(_MOVE_EVENTS_PATTERN)
                await pubsub.subscribe(_CHAT_CHANNEL)
                async for msg in pubsub.listen():
                    if self._stop.is_set():
                        break
                    mtype = msg.get("type")
                    if mtype not in ("message", "pmessage"):
                        continue
                    await self._handle(msg)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("[events_subscriber] error, restarting in 2s: %s", exc)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    continue

    async def _handle(self, msg: dict) -> None:
        sid = get_active_session_id()
        if not sid:
            return  # nothing to attribute the event to
        channel = msg.get("channel", "")
        raw = msg.get("data", "")
        try:
            payload = json.loads(raw) if isinstance(raw, str) else {}
        except json.JSONDecodeError:
            payload = {"text": str(raw)}

        if channel == _CHAT_CHANNEL:
            append_event(
                sid,
                registration=payload.get("registration"),
                event=payload.get("kind", "chat"),
                extra={
                    "sender": payload.get("sender"),
                    "callsign": payload.get("callsign"),
                    "text": payload.get("text"),
                },
            )
            return

        # aircraft:{reg}:move_events
        reg = None
        parts = channel.split(":")
        if len(parts) >= 3:
            reg = parts[1]
        append_event(
            sid,
            registration=reg,
            event=str(payload.get("event", "event")),
            extra={k: v for k, v in payload.items() if k not in ("event", "ts")},
        )


_subscriber = EventsSubscriber()


async def start_subscriber() -> None:
    await _subscriber.start()


async def stop_subscriber() -> None:
    await _subscriber.stop()
