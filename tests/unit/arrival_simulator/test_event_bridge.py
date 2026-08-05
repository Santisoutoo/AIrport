"""Unit tests for services/arrival_simulator_service/core/event_bridge.py.

This bridge listens on Redis pub/sub for AircraftMover events and translates
them into pilot radio calls (pushed to ``tts:queue``) so the controller
hears the right phrase at the right time.

We test ``_handle_event`` in isolation -- the async pub/sub loop is just a
reconnect wrapper.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from core import event_bridge


@pytest.fixture(autouse=True)
def _reset_active_arrivals():
    """Avoid cross-test pollution of the module-level _active_arrivals dict."""
    event_bridge._active_arrivals.clear()
    yield
    event_bridge._active_arrivals.clear()


@pytest.fixture
def captured_tts(monkeypatch):
    """Capture _push_tts calls without actually invoking asyncio.create_task."""
    captured = []

    def _capture(text):
        captured.append(text)

    monkeypatch.setattr(event_bridge, "_push_tts", _capture)
    return captured


# ---------------------------------------------------------------------------
# request_landing
# ---------------------------------------------------------------------------


def test_handle_request_landing_pushes_tts_with_pilot_phrase(captured_tts):
    event_bridge.register_arrival({"registration": "EC-NEW", "callsign": "VLG1234", "runway": "17"})

    event_bridge._handle_event("EC-NEW", {"event": "request_landing", "dme_nm": 4.0})

    assert len(captured_tts) == 1
    assert captured_tts[0] == "Tower, VLG1234, 4 miles final runway 17, request landing."


def test_handle_request_landing_rounds_dme_to_int(captured_tts):
    """DME from the mover is a float; the phrase must read as an integer mile count."""
    event_bridge.register_arrival({"registration": "EC-NEW", "callsign": "VLG1234", "runway": "35"})

    event_bridge._handle_event("EC-NEW", {"event": "request_landing", "dme_nm": 3.8})

    assert "4 miles final" in captured_tts[0]


def test_handle_request_landing_accepts_string_dme(captured_tts):
    """A stringified DME from the JSON payload must still parse cleanly."""
    event_bridge.register_arrival({"registration": "EC-NEW", "callsign": "VLG1234", "runway": "17"})

    event_bridge._handle_event("EC-NEW", {"event": "request_landing", "dme_nm": "4"})

    assert "4 miles final" in captured_tts[0]


def test_handle_invalid_dme_value_raises_or_skips_gracefully(captured_tts):
    """Garbled DME must not crash the whole pub/sub loop -- at worst, no TTS is pushed.

    The current implementation (float('not-a-num')) raises, so we just verify
    that the surrounding loop's exception handler (in run_bridge) would catch it.
    """
    event_bridge.register_arrival({"registration": "EC-NEW", "callsign": "VLG1234", "runway": "17"})

    with pytest.raises(ValueError):
        event_bridge._handle_event("EC-NEW", {"event": "request_landing", "dme_nm": "not-a-num"})


# ---------------------------------------------------------------------------
# rolling_out
# ---------------------------------------------------------------------------


def test_handle_rolling_out_pushes_vacating_phrase(captured_tts):
    event_bridge.register_arrival({"registration": "EC-NEW", "callsign": "VLG1234", "runway": "17"})

    event_bridge._handle_event("EC-NEW", {"event": "rolling_out"})

    assert captured_tts == ["VLG1234 vacating runway 17."]


# ---------------------------------------------------------------------------
# reached_end
# ---------------------------------------------------------------------------


def test_handle_reached_end_unregisters_arrival(captured_tts):
    event_bridge.register_arrival({"registration": "EC-NEW", "callsign": "VLG1234", "runway": "17"})
    assert "EC-NEW" in event_bridge._active_arrivals

    event_bridge._handle_event("EC-NEW", {"event": "reached_end"})

    assert "EC-NEW" not in event_bridge._active_arrivals


def test_handle_reached_end_notifies_scheduler():
    """If the scheduler module is importable, remove_arrival is called."""
    event_bridge.register_arrival({"registration": "EC-NEW", "callsign": "VLG1234", "runway": "17"})

    with patch("core.scheduler.get_scheduler") as mock_get:
        mock_scheduler = mock_get.return_value
        event_bridge._handle_event("EC-NEW", {"event": "reached_end"})
        mock_scheduler.remove_arrival.assert_called_once_with("EC-NEW")


def test_handle_reached_end_swallows_scheduler_failure():
    """Failure to notify the scheduler must NOT propagate."""
    event_bridge.register_arrival({"registration": "EC-NEW", "callsign": "VLG1234", "runway": "17"})

    with patch("core.scheduler.get_scheduler", side_effect=RuntimeError("no scheduler")):
        # Must not raise
        event_bridge._handle_event("EC-NEW", {"event": "reached_end"})

    # Arrival is still unregistered
    assert "EC-NEW" not in event_bridge._active_arrivals


# ---------------------------------------------------------------------------
# Unknown registration / unknown event
# ---------------------------------------------------------------------------


def test_handle_event_for_unregistered_reg_is_noop(captured_tts):
    """An event for an aircraft not registered as an arrival is ignored."""
    event_bridge._handle_event("EC-UNKNOWN", {"event": "request_landing", "dme_nm": 4.0})
    assert captured_tts == []


def test_handle_event_with_unknown_event_kind_is_silent(captured_tts):
    event_bridge.register_arrival({"registration": "EC-NEW", "callsign": "VLG1234", "runway": "17"})

    event_bridge._handle_event("EC-NEW", {"event": "something_else"})

    assert captured_tts == []


def test_register_and_unregister_helpers():
    """The public register/unregister APIs must be symmetrical."""
    meta = {"registration": "EC-X", "callsign": "FOO", "runway": "17"}
    event_bridge.register_arrival(meta)
    assert event_bridge._active_arrivals["EC-X"] is meta

    event_bridge.unregister_arrival("EC-X")
    assert "EC-X" not in event_bridge._active_arrivals


def test_unregister_arrival_is_idempotent():
    """Calling unregister twice (or for an unknown reg) must not raise."""
    event_bridge.unregister_arrival("NEVER-REGISTERED")  # no-op
    event_bridge.unregister_arrival("NEVER-REGISTERED")  # still no-op
