"""WebSocket endpoint for the controller chat panel.

Subscribes to the Redis `hmi:chat` Pub/Sub channel and fans out every
incoming payload to connected browser clients. Producers today:
- shared.services.taxi_router (rejection messages in the pilot's voice).
"""

import asyncio
import json
import logging
import os
from typing import Set

import redis.asyncio as redis_async
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/plugin", tags=["plugin-chat"])

_CHANNEL = "hmi:chat"
_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")


class _ChatBroadcaster:
    """Single Redis subscriber that fans out to every connected WebSocket."""

    def __init__(self):
        self._clients: Set[WebSocket] = set()
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def attach(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.add(ws)
            if self._task is None or self._task.done():
                self._task = asyncio.create_task(self._pump())

    async def detach(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def _pump(self) -> None:
        try:
            client = redis_async.from_url(_REDIS_URL, decode_responses=True)
            pubsub = client.pubsub()
            await pubsub.subscribe(_CHANNEL)
            logger.info("[HMI chat] subscribed to %s", _CHANNEL)
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                raw = message.get("data") or ""
                try:
                    payload = json.loads(raw) if isinstance(raw, str) else raw
                except json.JSONDecodeError:
                    payload = {"text": str(raw), "sender": "pilot"}
                await self._broadcast(payload)
        except Exception as exc:
            logger.exception("[HMI chat] pump error: %s", exc)

    async def _broadcast(self, payload: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.detach(ws)


_broadcaster = _ChatBroadcaster()


@router.websocket("/chat/stream")
async def chat_stream(ws: WebSocket):
    await ws.accept()
    await _broadcaster.attach(ws)
    try:
        while True:
            # Clients may push outgoing controller messages later; for now,
            # just keep the connection alive and discard anything received.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await _broadcaster.detach(ws)
