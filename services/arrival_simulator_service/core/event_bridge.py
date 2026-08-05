"""Listens to AircraftMover events on Redis pub/sub and turns them into
pilot radio calls when an arrival crosses key milestones.

The mover publishes events to `aircraft:{reg}:move_events`. When an
arrival aircraft reaches the request-landing DME (4 NM), it emits
`request_landing`. This bridge translates that into a pre-formatted TTS
phrase pushed to `tts:queue` so the controller (user) hears it.
"""

import asyncio
import json
import logging
import os

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
_TTS_QUEUE = "tts:queue"
_EVENT_PATTERN = "aircraft:*:move_events"

# Track which regs are arrivals (so we can shape the pilot phrase).
_active_arrivals: dict[str, dict] = {}


def register_arrival(meta: dict) -> None:
    """Called by the planner after dispatch so the bridge knows the callsign+runway."""
    _active_arrivals[meta["registration"]] = meta


def unregister_arrival(reg: str) -> None:
    _active_arrivals.pop(reg, None)


def _handle_event(reg: str, payload: dict) -> None:
    event = payload.get("event")
    meta = _active_arrivals.get(reg)
    if meta is None:
        return  # not an arrival we care about (e.g. departure taxi)

    if event == "request_landing":
        dme = payload.get("dme_nm", "")
        text = (
            f"Tower, {meta['callsign']}, {int(round(float(dme)))} miles final runway {meta['runway']}, request landing."
        )
        _push_tts(text)
        logger.info("Pilot request published for %s: %s", reg, text)

    elif event == "rolling_out":
        text = f"{meta['callsign']} vacating runway {meta['runway']}."
        _push_tts(text)

    elif event == "reached_end":
        logger.info("Arrival %s reached end of plan — freeing slot", reg)
        unregister_arrival(reg)
        # Notify scheduler so it can fill the freed slot on the next check.
        try:
            from .scheduler import get_scheduler

            get_scheduler().remove_arrival(reg)
        except Exception:  # noqa: BLE001
            pass


def _push_tts(text: str) -> None:
    r = aioredis.from_url(_REDIS_URL, decode_responses=True)
    asyncio.create_task(_push_tts_async(r, text))


async def _push_tts_async(r: aioredis.Redis, text: str) -> None:
    try:
        await r.rpush(_TTS_QUEUE, json.dumps({"text": text}))
    finally:
        await r.aclose()


async def run_bridge(stop_event: asyncio.Event) -> None:
    """Subscribe to mover events and dispatch handlers until stop_event is set."""
    r = aioredis.from_url(_REDIS_URL, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.psubscribe(_EVENT_PATTERN)
    logger.info("Event bridge subscribed to %s", _EVENT_PATTERN)
    try:
        while not stop_event.is_set():
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg is None:
                continue
            channel = msg.get("channel", "")
            parts = channel.split(":")
            if len(parts) < 3:
                continue
            reg = parts[1]
            try:
                payload = json.loads(msg.get("data") or "{}")
            except json.JSONDecodeError:
                continue
            try:
                _handle_event(reg, payload)
            except Exception as exc:  # noqa: BLE001
                logger.exception("event handler failed for %s: %s", reg, exc)
    finally:
        await pubsub.punsubscribe(_EVENT_PATTERN)
        await pubsub.aclose()
        await r.aclose()
        logger.info("Event bridge stopped")
