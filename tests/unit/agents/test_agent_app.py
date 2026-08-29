"""Unit tests for agents/common/agent_app.py — the generic pilot FastAPI app.

Covers the HTTP surface the orchestrator talks to: the request body it sends, the
response keys it reads back, and the two informational endpoints.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agents.common.agent_app import AgentAppConfig, create_app


DEL_CONFIG = AgentAppConfig(
    label="DEL",
    role="delivery",
    title="AIrport DEL Agent",
    version="0.2.0",
    description="ATC Delivery controller — issues IFR departure clearances",
    data_key="clearance_data",
    context_fields=("flight_plan", "atis"),
)

TWR_CONFIG = AgentAppConfig(
    label="TWR",
    role="tower",
    title="AIrport TWR Agent",
    version="0.1.0",
    description="Pilot on Tower frequency",
    data_key="reply_data",
    context_fields=("clearance_data",),
)


def _client(config, run_agent):
    return TestClient(create_app(config, run_agent))


def test_run_forwards_context_positionally_and_returns_the_data_key():
    seen = {}

    def run_agent(session_id, message, flight_plan=None, atis=None):
        seen.update(
            session_id=session_id, message=message, flight_plan=flight_plan, atis=atis
        )
        return {"reply": "Cleared to LEPA", "clearance_data": {"squawk": "2341"}}

    with _client(DEL_CONFIG, run_agent) as client:
        resp = client.post(
            "/agents/delivery/run",
            json={
                "session_id": "s1",
                "message": "request clearance",
                "flight_plan": {"id": 7},
                "atis": {"letter": "C"},
            },
        )

    assert resp.status_code == 200
    assert resp.json() == {
        "session_id": "s1",
        "reply": "Cleared to LEPA",
        "clearance_data": {"squawk": "2341"},
    }
    assert seen == {
        "session_id": "s1",
        "message": "request clearance",
        "flight_plan": {"id": 7},
        "atis": {"letter": "C"},
    }


def test_context_fields_are_optional():
    def run_agent(session_id, message, clearance_data=None):
        assert clearance_data is None
        return {"reply": "Runway 06R, cleared for takeoff", "reply_data": None}

    with _client(TWR_CONFIG, run_agent) as client:
        resp = client.post("/agents/tower/run", json={"session_id": "s1", "message": "hi"})

    assert resp.status_code == 200
    assert resp.json() == {
        "session_id": "s1",
        "reply": "Runway 06R, cleared for takeoff",
        "reply_data": None,
    }


def test_missing_message_is_a_validation_error():
    with _client(TWR_CONFIG, lambda *a: {}) as client:
        resp = client.post("/agents/tower/run", json={"session_id": "s1"})

    assert resp.status_code == 422


def test_runner_failure_surfaces_as_a_server_error():
    def run_agent(*_):
        raise RuntimeError("boom")

    with _client(TWR_CONFIG, run_agent) as client:
        with pytest.raises(RuntimeError):
            client.post("/agents/tower/run", json={"session_id": "s1", "message": "hi"})


def test_health_and_info_endpoints(monkeypatch):
    monkeypatch.setenv("AGENT_MODEL", "gemini-test")

    with _client(DEL_CONFIG, lambda *a: {}) as client:
        health = client.get("/health")
        info = client.get("/agents/delivery/info")

    assert health.json() == {"status": "ok", "model": "gemini-test"}
    assert info.json() == {
        "name": "DEL",
        "model": "gemini-test",
        "description": "ATC Delivery controller — issues IFR departure clearances",
    }


def test_openapi_metadata_matches_the_config():
    with _client(DEL_CONFIG, lambda *a: {}) as client:
        schema = client.get("/openapi.json").json()

    assert schema["info"]["title"] == "AIrport DEL Agent"
    assert schema["info"]["version"] == "0.2.0"
    assert "/agents/delivery/run" in schema["paths"]
