"""Unit tests for services/orchestrator_service/session_log.py.

The module owns three per-session Redis lists (transcripts, agent_replies,
events) with a 2-hour TTL. Every push is fire-and-forget -- if Redis goes
down, the function logs and returns without raising.

Tests use FakeRedis (tests/fixtures/fake_redis.py) and rebind
``session_log._client`` so the module talks to the fake.
"""

from __future__ import annotations

import json

import pytest

import session_log


@pytest.fixture(autouse=True)
def _patch_client(fake_redis, monkeypatch):
    """Force every session_log call to use the per-test FakeRedis."""
    # Reset the module-level cached client and override the factory
    monkeypatch.setattr(session_log, "_r", None)
    monkeypatch.setattr(session_log, "_client", lambda: fake_redis)
    monkeypatch.setattr(session_log, "_redis_client", lambda: fake_redis)
    yield


# ---------------------------------------------------------------------------
# append_transcript
# ---------------------------------------------------------------------------


def test_append_transcript_pushes_to_redis_with_ts_and_text(fake_redis):
    session_log.append_transcript("sess1", "Tower, EC-MIG, ready for takeoff")

    items = fake_redis.lists["session:sess1:transcripts"]
    assert len(items) == 1
    payload = json.loads(items[0])
    assert payload["text"] == "Tower, EC-MIG, ready for takeoff"
    assert "ts" in payload and isinstance(payload["ts"], float)


def test_append_transcript_noop_on_empty_text(fake_redis):
    session_log.append_transcript("sess1", "")
    session_log.append_transcript("sess1", None)  # type: ignore[arg-type]

    assert "session:sess1:transcripts" not in fake_redis.lists


def test_append_transcript_noop_on_empty_session_id(fake_redis):
    session_log.append_transcript("", "hello")
    session_log.append_transcript(None, "hello")  # type: ignore[arg-type]

    # No list should be created
    assert not any(k.startswith("session:") for k in fake_redis.lists)


def test_append_transcript_sets_ttl_2h(fake_redis):
    session_log.append_transcript("sess1", "hi")
    assert fake_redis.expirations.get("session:sess1:transcripts") == 7200


def test_append_transcript_multiple_calls_accumulate(fake_redis):
    session_log.append_transcript("sess1", "first")
    session_log.append_transcript("sess1", "second")
    items = fake_redis.lists["session:sess1:transcripts"]
    assert len(items) == 2
    # LPUSH: newest first, so [0] is "second"
    assert json.loads(items[0])["text"] == "second"
    assert json.loads(items[1])["text"] == "first"


# ---------------------------------------------------------------------------
# append_agent_reply
# ---------------------------------------------------------------------------


def test_append_agent_reply_pushes_full_payload(fake_redis):
    session_log.append_agent_reply(
        session_id="sess1",
        dep="DEL",
        registration="EC-MIG",
        callsign="IBE3421",
        reply="Cleared to LEPA",
    )
    items = fake_redis.lists["session:sess1:agent_replies"]
    assert len(items) == 1
    payload = json.loads(items[0])
    assert payload["dep"] == "DEL"
    assert payload["registration"] == "EC-MIG"
    assert payload["callsign"] == "IBE3421"
    assert payload["reply"] == "Cleared to LEPA"
    assert payload["taxi_data"] is None


def test_append_agent_reply_includes_taxi_data(fake_redis):
    taxi = {"taxi_route": "T, E1", "pushback_approved": True}
    session_log.append_agent_reply(
        session_id="sess1",
        dep="GND",
        registration="EC-MIG",
        callsign="IBE3421",
        reply="Push approved",
        taxi_data=taxi,
    )
    items = fake_redis.lists["session:sess1:agent_replies"]
    payload = json.loads(items[0])
    assert payload["taxi_data"] == taxi


def test_append_agent_reply_noop_on_empty_session_id(fake_redis):
    session_log.append_agent_reply("", "DEL", "EC-MIG", "IBE", "hello")
    assert not any(k.endswith(":agent_replies") for k in fake_redis.lists)


# ---------------------------------------------------------------------------
# append_event
# ---------------------------------------------------------------------------


def test_append_event_pushes_payload_with_extra(fake_redis):
    session_log.append_event(
        session_id="sess1",
        registration="EC-MIG",
        event="touchdown",
        extra={"runway": "17"},
    )
    items = fake_redis.lists["session:sess1:events"]
    assert len(items) == 1
    payload = json.loads(items[0])
    assert payload["event"] == "touchdown"
    assert payload["registration"] == "EC-MIG"
    assert payload["extra"] == {"runway": "17"}


def test_append_event_default_extra_is_empty_dict(fake_redis):
    session_log.append_event("sess1", "EC-MIG", "rolling_out")
    payload = json.loads(fake_redis.lists["session:sess1:events"][0])
    assert payload["extra"] == {}


def test_append_event_noop_on_empty_event(fake_redis):
    session_log.append_event("sess1", "EC-MIG", "")
    assert "session:sess1:events" not in fake_redis.lists


def test_append_event_noop_on_empty_session_id(fake_redis):
    session_log.append_event("", "EC-MIG", "touchdown")
    assert not fake_redis.lists


# ---------------------------------------------------------------------------
# Read helpers (get_transcripts, get_agent_replies, get_events)
# ---------------------------------------------------------------------------


def test_get_transcripts_returns_chronological_order(fake_redis):
    """LPUSHed messages are stored newest-first; readers must reverse to chrono."""
    session_log.append_transcript("sess1", "first")
    session_log.append_transcript("sess1", "second")
    session_log.append_transcript("sess1", "third")

    transcripts = session_log.get_transcripts("sess1")
    assert [t["text"] for t in transcripts] == ["first", "second", "third"]


def test_get_transcripts_returns_empty_when_no_session(fake_redis):
    assert session_log.get_transcripts("unknown-session") == []


def test_get_transcripts_skips_invalid_json_entries(fake_redis):
    """A corrupted entry must be silently skipped, not crash the reader."""
    fake_redis.lists["session:sess1:transcripts"] = ["not-json", json.dumps({"ts": 1, "text": "ok"})]
    transcripts = session_log.get_transcripts("sess1")
    assert len(transcripts) == 1
    assert transcripts[0]["text"] == "ok"


def test_get_agent_replies_chronological(fake_redis):
    session_log.append_agent_reply("sess1", "DEL", "EC-MIG", "IBE", "first")
    session_log.append_agent_reply("sess1", "GND", "EC-MIG", "IBE", "second")
    replies = session_log.get_agent_replies("sess1")
    assert [r["reply"] for r in replies] == ["first", "second"]


def test_get_events_chronological(fake_redis):
    session_log.append_event("sess1", "EC-MIG", "first")
    session_log.append_event("sess1", "EC-MIG", "second")
    events = session_log.get_events("sess1")
    assert [e["event"] for e in events] == ["first", "second"]


# ---------------------------------------------------------------------------
# get_active_session_id
# ---------------------------------------------------------------------------


def test_get_active_session_id_reads_from_hash(fake_redis):
    fake_redis.hset("airport:session_request", mapping={"session_id": "current-sess"})
    assert session_log.get_active_session_id() == "current-sess"


def test_get_active_session_id_returns_none_when_missing(fake_redis):
    assert session_log.get_active_session_id() is None


def test_get_active_session_id_returns_none_on_redis_error(fake_redis):
    """Best-effort: a Redis ConnectionError must not propagate."""
    fake_redis.fail_next("hget", times=10)
    # Need to patch hget directly since it's not in fail_next's default list of methods
    original_hget = fake_redis.hget

    def _raising_hget(*args, **kwargs):
        raise ConnectionError("redis down")

    fake_redis.hget = _raising_hget  # type: ignore[assignment]
    try:
        assert session_log.get_active_session_id() is None
    finally:
        fake_redis.hget = original_hget  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Resilience: Redis failures must not propagate to callers
# ---------------------------------------------------------------------------


def test_redis_failure_in_push_does_not_raise(fake_redis):
    """If Redis goes down, append_transcript logs and returns silently."""
    # Force the pipeline's execute() to fail by making lpush raise
    fake_redis.fail_next("lpush", times=10)

    # Must not raise
    session_log.append_transcript("sess1", "hello")
