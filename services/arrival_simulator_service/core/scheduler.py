"""Maintains a minimum number of concurrent AI arrival aircraft.

Every CHECK_INTERVAL_S the scheduler counts how many arrivals are still
active (in-flight or vacating) and dispatches as many new ones as needed
to reach MIN_CONCURRENT.  When an aircraft finishes its plan (reaches the
vacate point and parks) the event bridge calls `remove_arrival()` so the
slot opens up immediately for the next check cycle.
"""

import asyncio
import logging
import os

from . import event_bridge, plan_catalog
from .arrival_planner import dispatch_arrival
from .runway_config import get_active_runway

logger = logging.getLogger(__name__)

DEFAULT_MIN_CONCURRENT = int(os.getenv("ARRIVAL_MIN_CONCURRENT", "3"))
CHECK_INTERVAL_S = float(os.getenv("ARRIVAL_CHECK_INTERVAL_S", "15.0"))


class ArrivalScheduler:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._bridge_task: asyncio.Task | None = None
        self._min_concurrent: int = DEFAULT_MIN_CONCURRENT
        # Registrations currently in-flight (added on dispatch, removed on reached_end).
        self._active_regs: set[str] = set()
        # Full metadata list (for the /active endpoint).
        self._active_meta: dict[str, dict] = {}

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def min_concurrent(self) -> int:
        return self._min_concurrent

    @property
    def active(self) -> list[dict]:
        return list(self._active_meta.values())

    def remove_arrival(self, registration: str) -> None:
        """Called by event_bridge when an aircraft reaches the end of its plan."""
        self._active_regs.discard(registration)
        self._active_meta.pop(registration, None)
        logger.info("Arrival %s completed — %d still active", registration, len(self._active_regs))

    async def start(self, min_concurrent: int | None = None) -> None:
        if self.running:
            return
        if min_concurrent is not None:
            self._min_concurrent = max(1, int(min_concurrent))
        self._stop_event.clear()
        self._active_regs.clear()
        self._active_meta.clear()
        plan_catalog.reset_assignments()
        await _purge_stale_redis_keys()
        self._bridge_task = asyncio.create_task(event_bridge.run_bridge(self._stop_event))
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "ArrivalScheduler started (min_concurrent=%d, check_interval=%.1f s)",
            self._min_concurrent, CHECK_INTERVAL_S,
        )

    async def stop(self) -> None:
        if not self.running:
            return
        self._stop_event.set()
        await asyncio.gather(self._task, self._bridge_task, return_exceptions=True)
        self._task = None
        self._bridge_task = None
        plan_catalog.reset_assignments()
        logger.info("ArrivalScheduler stopped")

    async def _run_loop(self) -> None:
        runway = get_active_runway("LEST")
        while not self._stop_event.is_set():
            needed = max(0, self._min_concurrent - len(self._active_regs))
            for i in range(needed):
                if self._stop_event.is_set():
                    break
                try:
                    await self._dispatch_one(runway, slot_index=i)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Arrival dispatch failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=CHECK_INTERVAL_S)
            except asyncio.TimeoutError:
                continue

    async def _dispatch_one(self, runway, slot_index: int = 0) -> None:
        plan = await plan_catalog.fetch_pending_arrival(runway.icao)
        if plan is None:
            logger.info("No more pending arrivals for %s; slot stays empty.", runway.icao)
            return
        slot_sep = float(os.getenv("ARRIVAL_SLOT_SEP_NM", "5.0"))
        base_dist = float(os.getenv("ARRIVAL_SPAWN_DISTANCE_NM", "10.0"))
        spawn_dist = base_dist + slot_index * slot_sep
        meta = dispatch_arrival(plan, runway, spawn_distance_nm=spawn_dist)
        reg = meta["registration"]
        plan_catalog.mark_assigned(reg)
        event_bridge.register_arrival(meta)
        self._active_regs.add(reg)
        self._active_meta[reg] = meta
        logger.info(
            "Dispatched %s — active now: %d/%d",
            reg, len(self._active_regs), self._min_concurrent,
        )


async def _purge_stale_redis_keys() -> None:
    """Delete spawn_request and move_cmd keys left over from the previous session."""
    import redis as _redis
    r = _redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379"), decode_responses=True)
    for key in r.keys("aircraft:spawn_request:*"):
        r.delete(key)
    from .plan_catalog import _SYNTHETIC_POOL
    for p in _SYNTHETIC_POOL:
        r.delete(f"aircraft:{p['aircraft_registration']}:move_cmd")
    logger.info("Purged stale arrival Redis keys")


_scheduler: ArrivalScheduler | None = None


def get_scheduler() -> ArrivalScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = ArrivalScheduler()
    return _scheduler
