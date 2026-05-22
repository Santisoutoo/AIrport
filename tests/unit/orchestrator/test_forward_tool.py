"""Unit tests for agent/tools/forward.py::forward_to_agent.

This is the heaviest tool in the orchestrator: it orchestrates HTTP traffic
to four upstream services (DEL/GND/TWR sub-agents + flight_plan + weather),
extracts pre-cached clearance data from tool_context, optionally dispatches
a taxi plan, and writes results back into session state.

Strategy:
  * Use ``respx`` to mock every outgoing httpx call.
  * Patch ``_ROUTES``, ``_FLIGHT_PLAN_URL``, ``_WEATHER_URL`` (resolved at
    import time from env vars) to point at deterministic URLs.
  * Patch ``session_log.append_agent_reply`` and the lazy import of
    ``dispatch_taxi_plan`` to record calls without performing I/O.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
import respx

from agent.tools import forward as forward_mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def configured_urls(monkeypatch):
    """Point forward.py at deterministic URLs for the test."""
    monkeypatch.setitem(
        forward_mod._ROUTES, "DEL", ("http://del.test", "/agents/delivery/run")
    )
    monkeypatch.setitem(
        forward_mod._ROUTES, "GND", ("http://gnd.test", "/agents/ground/run")
    )
    monkeypatch.setitem(
        forward_mod._ROUTES, "TWR", ("http://twr.test", "/agents/tower/run")
    )
    monkeypatch.setattr(forward_mod, "_FLIGHT_PLAN_URL", "http://fp.test")
    monkeypatch.setattr(forward_mod, "_WEATHER_URL", "http://wx.test")
    yield


@pytest.fixture
def captured_log(monkeypatch):
    """Capture session_log.append_agent_reply calls."""
    captured = []

    def _capture(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(forward_mod, "append_agent_reply", _capture)
    return captured


@pytest.fixture
def captured_taxi_dispatch(monkeypatch):
    """Capture dispatch_taxi_plan calls (imported lazily inside forward_to_agent)."""
    captured = []

    def _capture(merged, **kwargs):
        captured.append({"merged": merged, "kwargs": kwargs})

    import sys
    import types

    # Build a fake module that exposes dispatch_taxi_plan
    fake_router = types.ModuleType("shared.services.taxi_router")
    fake_router.dispatch_taxi_plan = _capture
    # Keep other attributes (compute_taxi_route etc.) if the real module was loaded
    if "shared.services.taxi_router" in sys.modules:
        original = sys.modules["shared.services.taxi_router"]
        for attr in dir(original):
            if not attr.startswith("_") and not hasattr(fake_router, attr):
                setattr(fake_router, attr, getattr(original, attr))
    monkeypatch.setitem(sys.modules, "shared.services.taxi_router", fake_router)
    return captured


def _ctx(session_id="sess-1", known_aircraft=None):
    return SimpleNamespace(
        state={"session_id": session_id, "known_aircraft": known_aircraft or []}
    )


# ---------------------------------------------------------------------------
# DEL: pre-fetch of flight_plan + atis
# ---------------------------------------------------------------------------


@respx.mock
def test_forward_del_includes_flight_plan_and_atis_in_payload(configured_urls, captured_log):
    respx.get("http://fp.test/plans/EC-MIG").mock(
        return_value=httpx.Response(200, json={"departure_ICAO": "LEST", "callsign": "IBE"})
    )
    respx.get("http://wx.test/atis/LEST").mock(
        return_value=httpx.Response(200, json={"info": "ATIS-A"})
    )
    captured = respx.post("http://del.test/agents/delivery/run").mock(
        return_value=httpx.Response(200, json={"reply": "Cleared to LEPA"})
    )

    reply = forward_mod.forward_to_agent("DEL", "EC-MIG", "request startup", _ctx())

    assert reply == "Cleared to LEPA"
    body = captured.calls[0].request.read()
    import json

    payload = json.loads(body)
    assert payload["session_id"] == "sess-1"
    assert payload["message"] == "request startup"
    assert payload["flight_plan"] == {"departure_ICAO": "LEST", "callsign": "IBE"}
    assert payload["atis"] == {"info": "ATIS-A"}


@respx.mock
def test_forward_del_atis_skipped_when_no_departure_icao(configured_urls, captured_log):
    respx.get("http://fp.test/plans/EC-MIG").mock(
        return_value=httpx.Response(200, json={"callsign": "IBE"})
    )
    captured = respx.post("http://del.test/agents/delivery/run").mock(
        return_value=httpx.Response(200, json={"reply": "ok"})
    )

    forward_mod.forward_to_agent("DEL", "EC-MIG", "request startup", _ctx())

    import json
    payload = json.loads(captured.calls[0].request.read())
    assert payload["flight_plan"] == {"callsign": "IBE"}
    assert payload["atis"] is None  # ATIS request was skipped


@respx.mock
def test_forward_del_handles_flight_plan_404(configured_urls, captured_log):
    """A 404 flight plan must result in flight_plan=None, not a crash."""
    respx.get("http://fp.test/plans/EC-MIG").mock(return_value=httpx.Response(404))
    captured = respx.post("http://del.test/agents/delivery/run").mock(
        return_value=httpx.Response(200, json={"reply": "ok"})
    )

    forward_mod.forward_to_agent("DEL", "EC-MIG", "request startup", _ctx())

    import json
    payload = json.loads(captured.calls[0].request.read())
    assert payload["flight_plan"] is None
    assert payload["atis"] is None


# ---------------------------------------------------------------------------
# GND/TWR: pre-cached clearance from state
# ---------------------------------------------------------------------------


@respx.mock
def test_forward_gnd_includes_clearance_data_from_state(configured_urls, captured_log):
    """GND payload must contain clearance_data WITHOUT registration/dependency/source."""
    known = [
        {
            "registration": "EC-MIG",
            "dependency": "GND",
            "source": "db",
            "callsign": "IBE3421",
            "squawk": 4321,
            "runway_in_use": "17",
            "instrumental_departure": "VAR1A",
        }
    ]
    captured = respx.post("http://gnd.test/agents/ground/run").mock(
        return_value=httpx.Response(200, json={"reply": "Push approved"})
    )

    forward_mod.forward_to_agent(
        "GND", "EC-MIG", "request pushback", _ctx(known_aircraft=known)
    )

    import json
    payload = json.loads(captured.calls[0].request.read())
    cd = payload["clearance_data"]
    assert cd["callsign"] == "IBE3421"
    assert cd["squawk"] == 4321
    assert cd["runway_in_use"] == "17"
    # These three keys must be stripped
    assert "registration" not in cd
    assert "dependency" not in cd
    assert "source" not in cd


@respx.mock
def test_forward_gnd_merges_taxi_route_into_clearance_data(
    configured_urls, captured_log
):
    known = [{"registration": "EC-MIG", "dependency": "GND", "source": "db", "callsign": "IBE"}]
    taxi_route = {"success": True, "waypoints": [{"lat": 0, "lon": 0}]}
    captured = respx.post("http://gnd.test/agents/ground/run").mock(
        return_value=httpx.Response(200, json={"reply": "ok"})
    )

    forward_mod.forward_to_agent(
        "GND",
        "EC-MIG",
        "ready taxi",
        _ctx(known_aircraft=known),
        taxi_route=taxi_route,
    )

    import json
    payload = json.loads(captured.calls[0].request.read())
    assert payload["clearance_data"]["taxi_route"] == taxi_route


@respx.mock
def test_forward_gnd_skips_taxi_route_when_unsuccessful(configured_urls, captured_log):
    """If taxi_route.success is False, it must NOT be merged."""
    known = [{"registration": "EC-MIG", "dependency": "GND", "source": "db", "callsign": "IBE"}]
    captured = respx.post("http://gnd.test/agents/ground/run").mock(
        return_value=httpx.Response(200, json={"reply": "ok"})
    )

    forward_mod.forward_to_agent(
        "GND",
        "EC-MIG",
        "ready taxi",
        _ctx(known_aircraft=known),
        taxi_route={"success": False, "error": "no route"},
    )

    import json
    payload = json.loads(captured.calls[0].request.read())
    assert "taxi_route" not in payload["clearance_data"]


# ---------------------------------------------------------------------------
# Routing edge cases
# ---------------------------------------------------------------------------


@respx.mock
def test_forward_unknown_dependency_falls_back_to_del(configured_urls, captured_log):
    respx.get("http://fp.test/plans/EC-MIG").mock(return_value=httpx.Response(404))
    captured = respx.post("http://del.test/agents/delivery/run").mock(
        return_value=httpx.Response(200, json={"reply": "fallback ok"})
    )

    reply = forward_mod.forward_to_agent("WHO", "EC-MIG", "anything", _ctx())

    assert reply == "fallback ok"
    assert captured.called


def test_forward_missing_agent_url_returns_error_string(monkeypatch):
    monkeypatch.setitem(forward_mod._ROUTES, "GND", ("", "/agents/ground/run"))
    known = [{"registration": "EC-MIG", "callsign": "IBE"}]
    ctx = _ctx(known_aircraft=known)

    reply = forward_mod.forward_to_agent("GND", "EC-MIG", "anything", ctx)

    assert reply.startswith("[ERROR]")
    assert "GND agent is not configured" in reply


# ---------------------------------------------------------------------------
# HTTP error handling
# ---------------------------------------------------------------------------


@respx.mock
def test_forward_http_error_returns_error_string(configured_urls, captured_log):
    known = [{"registration": "EC-MIG", "callsign": "IBE"}]
    respx.post("http://gnd.test/agents/ground/run").mock(return_value=httpx.Response(500))

    reply = forward_mod.forward_to_agent(
        "GND", "EC-MIG", "anything", _ctx(known_aircraft=known)
    )

    assert reply.startswith("[ERROR]")
    assert "HTTP 500" in reply


@respx.mock
def test_forward_request_error_returns_unreachable_string(configured_urls, captured_log):
    known = [{"registration": "EC-MIG", "callsign": "IBE"}]
    respx.post("http://gnd.test/agents/ground/run").mock(side_effect=httpx.ConnectError("nope"))

    reply = forward_mod.forward_to_agent(
        "GND", "EC-MIG", "anything", _ctx(known_aircraft=known)
    )

    assert "could not reach" in reply
    assert "GND" in reply


# ---------------------------------------------------------------------------
# State writes
# ---------------------------------------------------------------------------


@respx.mock
def test_forward_writes_state_keys(configured_urls, captured_log):
    respx.get("http://fp.test/plans/EC-MIG").mock(return_value=httpx.Response(404))
    respx.post("http://del.test/agents/delivery/run").mock(
        return_value=httpx.Response(
            200, json={"reply": "Cleared", "clearance_data": {"squawk": 1111}}
        )
    )
    ctx = _ctx()

    forward_mod.forward_to_agent("DEL", "EC-MIG", "request startup", ctx)

    assert ctx.state["reply"] == "Cleared"
    assert ctx.state["dependency"] == "DEL"
    assert ctx.state["registration"] == "EC-MIG"
    assert ctx.state["clearance_data"] == {"squawk": 1111}


# ---------------------------------------------------------------------------
# session_log: agent reply persistence
# ---------------------------------------------------------------------------


@respx.mock
def test_forward_appends_agent_reply_to_session_log(configured_urls, captured_log):
    respx.get("http://fp.test/plans/EC-MIG").mock(return_value=httpx.Response(404))
    respx.post("http://del.test/agents/delivery/run").mock(
        return_value=httpx.Response(200, json={"reply": "Cleared to LEPA"})
    )

    forward_mod.forward_to_agent("DEL", "EC-MIG", "request startup", _ctx())

    assert len(captured_log) == 1
    assert captured_log[0]["dep"] == "DEL"
    assert captured_log[0]["registration"] == "EC-MIG"
    assert captured_log[0]["reply"] == "Cleared to LEPA"


@respx.mock
def test_forward_no_session_log_when_session_id_empty(configured_urls, captured_log):
    respx.get("http://fp.test/plans/EC-MIG").mock(return_value=httpx.Response(404))
    respx.post("http://del.test/agents/delivery/run").mock(
        return_value=httpx.Response(200, json={"reply": "Cleared"})
    )

    forward_mod.forward_to_agent("DEL", "EC-MIG", "msg", _ctx(session_id=""))

    assert captured_log == []


# ---------------------------------------------------------------------------
# GND taxi dispatch trigger
# ---------------------------------------------------------------------------


@respx.mock
def test_forward_gnd_triggers_dispatch_taxi_plan_when_pushback_approved(
    configured_urls, captured_log, captured_taxi_dispatch
):
    known = [{"registration": "EC-MIG", "callsign": "IBE"}]
    respx.post("http://gnd.test/agents/ground/run").mock(
        return_value=httpx.Response(
            200,
            json={
                "reply": "Push approved, taxi T to E1",
                "taxi_data": {"pushback_approved": True, "aircraft_registration": "IBE"},
            },
        )
    )

    forward_mod.forward_to_agent(
        "GND", "EC-MIG", "request pushback", _ctx(known_aircraft=known)
    )

    assert len(captured_taxi_dispatch) == 1
    assert captured_taxi_dispatch[0]["kwargs"]["registration"] == "EC-MIG"
    assert captured_taxi_dispatch[0]["kwargs"]["callsign"] == "IBE"


@respx.mock
def test_forward_gnd_triggers_dispatch_when_only_taxi_route_text(
    configured_urls, captured_log, captured_taxi_dispatch
):
    known = [{"registration": "EC-MIG", "callsign": "IBE"}]
    respx.post("http://gnd.test/agents/ground/run").mock(
        return_value=httpx.Response(
            200,
            json={
                "reply": "Taxi T to E1",
                "taxi_data": {"taxi_route": "T E1", "aircraft_registration": "IBE"},
            },
        )
    )

    forward_mod.forward_to_agent("GND", "EC-MIG", "ready taxi", _ctx(known_aircraft=known))

    assert len(captured_taxi_dispatch) == 1


@respx.mock
def test_forward_gnd_does_not_trigger_dispatch_without_taxi_data(
    configured_urls, captured_log, captured_taxi_dispatch
):
    known = [{"registration": "EC-MIG", "callsign": "IBE"}]
    respx.post("http://gnd.test/agents/ground/run").mock(
        return_value=httpx.Response(200, json={"reply": "OK"})
    )

    forward_mod.forward_to_agent("GND", "EC-MIG", "ack", _ctx(known_aircraft=known))

    assert captured_taxi_dispatch == []


@respx.mock
def test_forward_del_never_triggers_taxi_dispatch(
    configured_urls, captured_log, captured_taxi_dispatch
):
    """taxi dispatch is GND-only — DEL must never trigger it."""
    respx.get("http://fp.test/plans/EC-MIG").mock(return_value=httpx.Response(404))
    respx.post("http://del.test/agents/delivery/run").mock(
        return_value=httpx.Response(
            200,
            json={
                "reply": "Cleared",
                "taxi_data": {"pushback_approved": True},  # would trigger if GND
            },
        )
    )

    forward_mod.forward_to_agent("DEL", "EC-MIG", "request startup", _ctx())

    assert captured_taxi_dispatch == []


@respx.mock
def test_forward_dispatch_failure_is_swallowed(
    configured_urls, captured_log, monkeypatch
):
    """If dispatch_taxi_plan crashes, the forward call must still return normally."""
    known = [{"registration": "EC-MIG", "callsign": "IBE"}]
    respx.post("http://gnd.test/agents/ground/run").mock(
        return_value=httpx.Response(
            200,
            json={
                "reply": "OK",
                "taxi_data": {"pushback_approved": True, "aircraft_registration": "IBE"},
            },
        )
    )
    import sys
    import types

    fake_router = types.ModuleType("shared.services.taxi_router")
    fake_router.dispatch_taxi_plan = MagicMock(side_effect=RuntimeError("boom"))
    monkeypatch.setitem(sys.modules, "shared.services.taxi_router", fake_router)

    reply = forward_mod.forward_to_agent(
        "GND", "EC-MIG", "ready taxi", _ctx(known_aircraft=known)
    )

    assert reply == "OK"  # graceful: dispatch failure doesn't propagate
