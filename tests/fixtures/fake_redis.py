"""In-process FakeRedis implementation for unit + integration tests.

Replaces ``redis.Redis`` with a synchronous fake that supports the subset of
operations the AIrport code uses:

  * KV: get / set / setex / delete / keys(pattern)
  * Hash: hset(mapping=) / hget / hgetall
  * Set: sadd / smembers / srem / sismember
  * List: lpush / rpush / lrange / llen
  * Pub/Sub: publish(channel, msg) and pubsub().psubscribe(pattern)
  * pipeline().execute()
  * expire(key, ttl) (records expirations for assertions)

It is intentionally tiny — no TTL eviction, no concurrency, no error injection
unless a test calls ``fake.fail_next("rpush")`` to make the next call raise.
"""

from __future__ import annotations

import fnmatch
import json
from collections import defaultdict
from typing import Any

import pytest


class _Pipeline:
    """Mimic redis.client.Pipeline — records calls, executes on `execute()`."""

    def __init__(self, parent: "FakeRedis"):
        self._parent = parent
        self._ops: list[tuple[str, tuple, dict]] = []

    def _enqueue(self, name: str):
        def _method(*args, **kwargs):
            self._ops.append((name, args, kwargs))
            return self

        return _method

    # Delegate any redis-like attribute to a recorder
    def __getattr__(self, name: str):
        return self._enqueue(name)

    def execute(self):
        results = []
        for name, args, kwargs in self._ops:
            results.append(getattr(self._parent, name)(*args, **kwargs))
        self._ops.clear()
        return results

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _PubSub:
    """Synchronous pub/sub stub.

    Tests can call ``fake_redis.publish(channel, msg)`` and the messages will
    be collected per channel. ``psubscribe(pattern)`` and ``get_message()``
    are provided for tests that exercise EventsSubscriber._handle directly.
    """

    def __init__(self, parent: "FakeRedis"):
        self._parent = parent
        self._patterns: list[str] = []
        self._buffer: list[dict] = []

    def psubscribe(self, *patterns: str):
        for p in patterns:
            self._patterns.append(p)
            self._parent._pubsubs.append(self)

    def subscribe(self, *channels: str):
        # Treat as exact pattern
        self.psubscribe(*channels)

    def get_message(self, ignore_subscribe_messages: bool = True, timeout: float = 0.0):
        if not self._buffer:
            return None
        return self._buffer.pop(0)

    async def listen(self):  # pragma: no cover - async iter helper
        for msg in list(self._buffer):
            yield msg

    def close(self):
        if self in self._parent._pubsubs:
            self._parent._pubsubs.remove(self)

    def deliver(self, channel: str, data: Any):
        for pat in self._patterns:
            if fnmatch.fnmatch(channel, pat):
                self._buffer.append(
                    {
                        "type": "pmessage" if "*" in pat else "message",
                        "pattern": pat if "*" in pat else None,
                        "channel": channel,
                        "data": data,
                    }
                )
                return


class FakeRedis:
    """Minimal in-memory Redis stand-in. Single-threaded, no eviction."""

    def __init__(self, *_, **__):
        self.kv: dict[str, Any] = {}
        self.hashes: dict[str, dict[str, Any]] = defaultdict(dict)
        self.sets: dict[str, set] = defaultdict(set)
        self.lists: dict[str, list] = defaultdict(list)
        self.published: dict[str, list] = defaultdict(list)
        self.expirations: dict[str, int] = {}
        self._fail_next: dict[str, int] = defaultdict(int)
        self._pubsubs: list[_PubSub] = []

    # ---- test helpers -----------------------------------------------------

    def fail_next(self, method: str, times: int = 1):
        """Make the next ``times`` calls to ``method`` raise ConnectionError."""
        self._fail_next[method] += times

    def _maybe_fail(self, method: str):
        if self._fail_next[method] > 0:
            self._fail_next[method] -= 1
            raise ConnectionError(f"FakeRedis: simulated failure in {method}")

    # ---- KV --------------------------------------------------------------

    def get(self, key: str):
        self._maybe_fail("get")
        return self.kv.get(key)

    def set(self, key: str, value: Any, ex: int | None = None, **__):
        self._maybe_fail("set")
        self.kv[key] = value
        if ex is not None:
            self.expirations[key] = ex
        return True

    def setex(self, key: str, ttl: int, value: Any):
        self._maybe_fail("setex")
        self.kv[key] = value
        self.expirations[key] = ttl
        return True

    def delete(self, *keys: str):
        self._maybe_fail("delete")
        n = 0
        for k in keys:
            for store in (self.kv, self.hashes, self.sets, self.lists):
                if k in store:
                    del store[k]
                    n += 1
                    break
        return n

    def keys(self, pattern: str = "*"):
        self._maybe_fail("keys")
        seen = set()
        for store in (self.kv, self.hashes, self.sets, self.lists):
            seen.update(store.keys())
        return [k for k in seen if fnmatch.fnmatch(k, pattern)]

    def expire(self, key: str, ttl: int):
        self._maybe_fail("expire")
        self.expirations[key] = ttl
        return True

    def exists(self, *keys: str):
        n = 0
        for k in keys:
            if (
                k in self.kv
                or k in self.hashes
                or k in self.sets
                or k in self.lists
            ):
                n += 1
        return n

    # ---- Hash ------------------------------------------------------------

    def hset(self, name: str, key: str | None = None, value: Any = None, mapping: dict | None = None):
        self._maybe_fail("hset")
        h = self.hashes[name]
        if mapping:
            h.update(mapping)
            return len(mapping)
        h[key] = value
        return 1

    def hget(self, name: str, key: str):
        return self.hashes.get(name, {}).get(key)

    def hgetall(self, name: str):
        return dict(self.hashes.get(name, {}))

    # ---- Set -------------------------------------------------------------

    def sadd(self, name: str, *members):
        self._maybe_fail("sadd")
        s = self.sets[name]
        added = 0
        for m in members:
            if m not in s:
                s.add(m)
                added += 1
        return added

    def smembers(self, name: str):
        self._maybe_fail("smembers")
        return set(self.sets.get(name, set()))

    def srem(self, name: str, *members):
        s = self.sets.get(name)
        if not s:
            return 0
        n = 0
        for m in members:
            if m in s:
                s.remove(m)
                n += 1
        return n

    def sismember(self, name: str, member):
        return member in self.sets.get(name, set())

    # ---- List ------------------------------------------------------------

    def lpush(self, name: str, *values):
        self._maybe_fail("lpush")
        for v in values:
            self.lists[name].insert(0, v)
        return len(self.lists[name])

    def rpush(self, name: str, *values):
        self._maybe_fail("rpush")
        for v in values:
            self.lists[name].append(v)
        return len(self.lists[name])

    def lrange(self, name: str, start: int, end: int):
        items = self.lists.get(name, [])
        if end == -1:
            return list(items[start:])
        return list(items[start : end + 1])

    def llen(self, name: str):
        return len(self.lists.get(name, []))

    # ---- Pub/Sub ---------------------------------------------------------

    def publish(self, channel: str, message: Any):
        self._maybe_fail("publish")
        # Store for assertions
        self.published[channel].append(message)
        # Deliver to active subscribers
        for ps in list(self._pubsubs):
            ps.deliver(channel, message)
        return len(self._pubsubs)

    def pubsub(self, *_, **__):
        return _PubSub(self)

    # ---- Pipeline --------------------------------------------------------

    def pipeline(self, transaction: bool = True):
        return _Pipeline(self)

    # ---- Misc helpers used by code --------------------------------------

    def ping(self):
        return True

    def close(self):
        pass

    @classmethod
    def from_url(cls, url: str, decode_responses: bool = False, **__):
        return cls()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_redis() -> FakeRedis:
    """Fresh FakeRedis instance per test."""
    return FakeRedis()
