"""Unit tests for api/events_subscriber.py::EventsSubscriber._handle.

We test _handle in isolation (without spinning up the Redis pub/sub loop)
because the loop logic is just a reconnection wrapper around _handle. Any
regression in routing, channel parsing, or payload formatting will surface
here.
"""

from __future__ import annotations

import json

import pytest
from api.events_subscriber import _CHAT_CHANNEL, EventsSubscriber


@pytest.fixture(autouse=True)
def _capture_events(monkeypatch):
    """Capture session_log.append_event calls instead of pushing to Redis."""
    captured = []

    def _capture(sid, registration, event, extra=None):
        captured.append({"sid": sid, "registration": registration, "event": event, "extra": extra})

    # Patch where events_subscriber imports it
    import api.events_subscriber as es

    monkeypatch.setattr(es, "append_event", _capture)
    return captured


@pytest.fixture
def session_active(monkeypatch):
    """Make get_active_session_id return a known id."""
    import api.events_subscriber as es

    monkeypatch.setattr(es, "get_active_session_id", lambda: "sess-abc")


@pytest.fixture
def session_inactive(monkeypatch):
    import api.events_subscriber as es

    monkeypatch.setattr(es, "get_active_session_id", lambda: None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_handle_chat_message_calls_append_event_with_text(session_active, _capture_events):
    sub = EventsSubscriber()
    payload = {
        "sender": "controller",
        "callsign": "IBE3421",
        "registration": "EC-MIG",
        "text": "request startup",
        "kind": "transmission",
    }
    msg = {
        "type": "message",
        "channel": _CHAT_CHANNEL,
        "data": json.dumps(payload),
    }
    await sub._handle(msg)

    assert len(_capture_events) == 1
    ev = _capture_events[0]
    assert ev["sid"] == "sess-abc"
    assert ev["registration"] == "EC-MIG"
    assert ev["event"] == "transmission"
    assert ev["extra"]["text"] == "request startup"
    assert ev["extra"]["sender"] == "controller"


async def test_handle_chat_message_with_kind_missing_defaults_to_chat(session_active, _capture_events):
    msg = {
        "type": "message",
        "channel": _CHAT_CHANNEL,
        "data": json.dumps({"text": "hi"}),
    }
    await EventsSubscriber()._handle(msg)
    assert _capture_events[0]["event"] == "chat"


async def test_handle_move_event_extracts_registration_from_channel(session_active, _capture_events):
    msg = {
        "type": "pmessage",
        "channel": "aircraft:EC-MIG:move_events",
        "data": json.dumps({"event": "touchdown", "runway": "17"}),
    }
    await EventsSubscriber()._handle(msg)

    ev = _capture_events[0]
    assert ev["registration"] == "EC-MIG"
    assert ev["event"] == "touchdown"
    assert ev["extra"] == {"runway": "17"}


async def test_handle_move_event_strips_event_and_ts_from_extra(session_active, _capture_events):
    msg = {
        "type": "pmessage",
        "channel": "aircraft:EC-MIG:move_events",
        "data": json.dumps({"event": "request_landing", "ts": 1234.5, "dme_nm": 4.0}),
    }
    await EventsSubscriber()._handle(msg)
    extra = _capture_events[0]["extra"]
    assert "event" not in extra
    assert "ts" not in extra
    assert extra["dme_nm"] == 4.0


async def test_handle_short_channel_yields_no_registration(session_active, _capture_events):
    """A channel without three colon-parts must NOT crash, just leave reg=None."""
    msg = {
        "type": "pmessage",
        "channel": "aircraft",
        "data": json.dumps({"event": "x"}),
    }
    await EventsSubscriber()._handle(msg)

    assert _capture_events[0]["registration"] is None


async def test_handle_invalid_json_in_chat_treats_as_text_payload(session_active, _capture_events):
    """A non-JSON data payload on the chat channel must fall back to {"text": <raw>}."""
    msg = {"type": "message", "channel": _CHAT_CHANNEL, "data": "plain text"}
    await EventsSubscriber()._handle(msg)

    ev = _capture_events[0]
    # The exception handler builds {"text": str(raw)} -- exact behavior we pin here
    assert ev["extra"]["text"] == "plain text"


async def test_handle_no_active_session_returns_early(session_inactive, _capture_events):
    """When no session is active, _handle returns without recording anything."""
    msg = {
        "type": "message",
        "channel": _CHAT_CHANNEL,
        "data": json.dumps({"text": "hi"}),
    }
    await EventsSubscriber()._handle(msg)

    assert _capture_events == []


async def test_handle_non_string_data_results_in_empty_payload(session_active, _capture_events):
    """If data is bytes (or anything non-str), payload defaults to {}."""
    msg = {
        "type": "pmessage",
        "channel": "aircraft:EC-MIG:move_events",
        "data": b"binary-blob",
    }
    await EventsSubscriber()._handle(msg)
    # event defaults to "event" when payload has no event key
    assert _capture_events[0]["event"] == "event"
    assert _capture_events[0]["extra"] == {}
