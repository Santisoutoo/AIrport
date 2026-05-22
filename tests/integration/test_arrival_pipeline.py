"""Integration test: full ARRIVAL pipeline APP → TWR → GND reverse handoff.

Models one inbound aircraft from arrival registration to taxi-in:
  1. POST /api/v1/orchestrator/arrivals/register → row with dependency='APP'
  2. event_bridge handles request_landing → TTS phrase queued
  3. "VLG1234 cleared to land runway 17" → TWR sub-agent reply
  4. event_bridge handles rolling_out → vacating TTS phrase
  5. "VLG1234 contact ground 121.9" → reverse handoff (currently xfail bug)
  6. event_bridge handles reached_end → arrival unregistered

All Redis, HTTP, ADK Runner traffic is mocked. The two known runner.py
bugs (advance_to_twr and advance_to_gnd_arrival not propagated) are
documented with xfail at the unit-test level (see test_runner.py); this
integration test still asserts the observable response shape.
"""

from __future__ import annotations

import json
import types

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.dispatch as dispatch_mod
import runner as runner_mod
import session_log as session_log_mod
from agent.tools import forward as forward_mod
from agent.tools.advance_to_gnd_arrival import advance_to_gnd_arrival
from api.arrivals import router as arrivals_router
from api.dispatch import router as dispatch_router
from core import event_bridge
from db.connection import get_db
from db.models import AircraftClearance
from tests.fixtures.adk_runner import install_fake_runner


pytestmark = pytest.mark.slow


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_event_bridge_state():
    event_bridge._active_arrivals.clear()
    yield
    event_bridge._active_arrivals.clear()


@pytest.fixture
def wire_pipeline(monkeypatch, fake_redis, db_session):
    fake_redis_module = types.SimpleNamespace(
        Redis=lambda *a, **kw: fake_redis,
        from_url=lambda url, **kw: fake_redis,
    )
    monkeypatch.setattr(runner_mod, "redis_lib", fake_redis_module)
    monkeypatch.setattr(dispatch_mod, "_redis", fake_redis_module)
    monkeypatch.setattr(session_log_mod, "_r", None)
    monkeypatch.setattr(session_log_mod, "_client", lambda: fake_redis)
    monkeypatch.setattr(session_log_mod, "_redis_client", lambda: fake_redis)

    monkeypatch.setitem(forward_mod._ROUTES, "TWR", ("http://twr.test", "/agents/tower/run"))
    monkeypatch.setattr(forward_mod, "_FLIGHT_PLAN_URL", "")
    monkeypatch.setattr(runner_mod, "_FLIGHT_PLAN_URL", "")

    # event_bridge._push_tts uses asyncio — capture instead of dispatching
    tts_captured = []
    monkeypatch.setattr(event_bridge, "_push_tts", lambda text: tts_captured.append(text))

    fake_runner = install_fake_runner(monkeypatch, runner_mod)

    return types.SimpleNamespace(
        fake_runner=fake_runner,
        tts_captured=tts_captured,
        fake_redis=fake_redis,
        db_session=db_session,
    )


@pytest.fixture
def client(wire_pipeline, db_session):
    app = FastAPI()
    app.include_router(dispatch_router)
    app.include_router(arrivals_router)

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


@respx.mock
def test_arrival_full_pipeline_app_to_twr_to_gnd(wire_pipeline, client, db_session):
    fake_runner = wire_pipeline.fake_runner
    tts_captured = wire_pipeline.tts_captured

    # -------------------------------------------------------------------
    # Step 1: arrival registers itself with the orchestrator
    # -------------------------------------------------------------------
    resp = client.post(
        "/api/v1/orchestrator/arrivals/register",
        json={
            "aircraft_registration": "VLG1234",
            "callsign": "VLG1234",
            "destination_icao": "LEST",
            "runway_in_use": "17",
        },
    )
    assert resp.status_code == 201
    assert resp.json() == {"registered": "VLG1234", "dependency": "APP"}

    row = db_session.query(AircraftClearance).filter_by(aircraft_registration="VLG1234").one()
    assert row.dependency == "APP"
    assert row.runway_in_use == "17"

    # Simulate the arrival_planner registering the bridge so events get routed
    event_bridge.register_arrival(
        {"registration": "VLG1234", "callsign": "VLG1234", "runway": "17"}
    )

    # -------------------------------------------------------------------
    # Step 2: mover emits request_landing → TTS pushed
    # -------------------------------------------------------------------
    event_bridge._handle_event("VLG1234", {"event": "request_landing", "dme_nm": 4.0})
    assert tts_captured[-1] == "Tower, VLG1234, 4 miles final runway 17, request landing."

    # -------------------------------------------------------------------
    # Step 3: controller issues landing clearance → TWR sub-agent
    # -------------------------------------------------------------------
    twr_call = respx.post("http://twr.test/agents/tower/run").mock(
        return_value=httpx.Response(
            200, json={"reply": "VLG1234, cleared to land runway 17."}
        )
    )

    def _step3_state(state):
        forward_mod.forward_to_agent(
            "TWR",
            "VLG1234",
            "VLG1234 cleared to land runway 17",
            types.SimpleNamespace(state=state),
        )

    fake_runner.script(state_updates=_step3_state, final_text="Cleared to land")
    resp = client.post(
        "/dispatch",
        json={"session_id": "sess-1", "message": "VLG1234 cleared to land runway 17"},
    )
    assert resp.status_code == 200
    # Forward does NOT advance the dependency in DB — it stays at APP
    db_session.expire_all()
    row = db_session.query(AircraftClearance).filter_by(aircraft_registration="VLG1234").one()
    assert row.dependency == "APP"
    assert twr_call.called

    # -------------------------------------------------------------------
    # Step 4: mover emits rolling_out → vacating TTS
    # -------------------------------------------------------------------
    event_bridge._handle_event("VLG1234", {"event": "rolling_out"})
    assert tts_captured[-1] == "VLG1234 vacating runway 17."

    # -------------------------------------------------------------------
    # Step 5: controller releases to GND (reverse handoff)
    # -------------------------------------------------------------------
    def _step5_state(state):
        # Pre-populate state.known_aircraft so the readback gets the callsign
        state["known_aircraft"] = [
            {"registration": "VLG1234", "callsign": "VLG1234"}
        ]
        advance_to_gnd_arrival(
            "VLG1234", "121.9", types.SimpleNamespace(state=state)
        )

    fake_runner.script(state_updates=_step5_state, final_text="121.9, VLG1234")
    resp = client.post(
        "/dispatch",
        json={
            "session_id": "sess-1",
            "message": "VLG1234 contact ground 121.9",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["agent"] == "GND"
    # The response carries the readback even though the DB row update is broken
    # by the known runner.py bug (see test_runner.py xfail tests).

    # -------------------------------------------------------------------
    # Step 6: reached_end unregisters and notifies the scheduler
    # -------------------------------------------------------------------
    assert "VLG1234" in event_bridge._active_arrivals
    event_bridge._handle_event("VLG1234", {"event": "reached_end"})
    assert "VLG1234" not in event_bridge._active_arrivals

    # -------------------------------------------------------------------
    # Side-effect totals
    # -------------------------------------------------------------------
    # Two TTS phrases from the bridge (request_landing + rolling_out) + two
    # dispatch replies (landing clearance + ground handoff) on the Redis queue.
    bridge_phrases = [t for t in tts_captured]
    assert len(bridge_phrases) == 2
    assert "request landing" in bridge_phrases[0]
    assert "vacating" in bridge_phrases[1]

    dispatch_tts = [json.loads(x)["text"] for x in wire_pipeline.fake_redis.lists["tts:queue"]]
    assert len(dispatch_tts) == 2
    assert "cleared to land" in dispatch_tts[0].lower()
    assert "121.9" in dispatch_tts[1]


def test_arrival_register_is_independent_of_event_bridge_state(
    wire_pipeline, client, db_session
):
    """Registering an arrival in the DB does NOT auto-register it in the event bridge."""
    client.post(
        "/api/v1/orchestrator/arrivals/register",
        json={"aircraft_registration": "EC-X"},
    )
    assert "EC-X" not in event_bridge._active_arrivals
    # An event for EC-X is silently ignored until register_arrival() is called
    event_bridge._handle_event("EC-X", {"event": "request_landing", "dme_nm": 4})
    assert wire_pipeline.tts_captured == []
