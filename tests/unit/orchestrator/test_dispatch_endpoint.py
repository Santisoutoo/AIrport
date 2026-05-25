"""Unit tests for api/dispatch.py -- POST /dispatch.

The endpoint:
  1. Appends the incoming pilot message to the session transcript log.
  2. Off-loads the LLM call to a ThreadPoolExecutor.
  3. RPUSHes the agent reply onto ``tts:queue`` so the TTS service speaks it.
  4. Returns DispatchResponse.

Each piece is exercised in isolation with FastAPI's TestClient. The runner
is replaced with a stub so we don't go through the real Google ADK loop.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.dispatch as dispatch_mod
import session_log
from api.dispatch import router as dispatch_router
from db.connection import get_db


@pytest.fixture
def app(db_session):
    application = FastAPI()
    application.include_router(dispatch_router)

    def _override_get_db():
        yield db_session

    application.dependency_overrides[get_db] = _override_get_db
    return application


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def stub_runner(monkeypatch):
    """Replace dispatch.run_orchestrator_agent with a programmable stub."""
    calls = []
    response_holder = {
        "result": {
            "reply": "Cleared to LEPA",
            "dependency": "DEL",
            "registration": "EC-MIG",
            "callsign": "IBE3421",
        }
    }

    def _stub(session_id, message, db):
        calls.append({"session_id": session_id, "message": message})
        result = response_holder.get("exc")
        if result is not None:
            raise result
        return response_holder["result"]

    monkeypatch.setattr(dispatch_mod, "run_orchestrator_agent", _stub)

    class _Handle:
        @staticmethod
        def set_result(result):
            response_holder["result"] = result
            response_holder.pop("exc", None)

        @staticmethod
        def raise_exception(exc):
            response_holder["exc"] = exc

        calls_list = calls

    return _Handle


@pytest.fixture
def stub_tts(monkeypatch, fake_redis):
    """Make ``_redis.from_url`` in dispatch.py return our FakeRedis."""
    import types

    fake_redis_module = types.SimpleNamespace(
        from_url=lambda url, **kw: fake_redis,
        Redis=lambda *a, **kw: fake_redis,
    )
    monkeypatch.setattr(dispatch_mod, "_redis", fake_redis_module)
    return fake_redis


@pytest.fixture
def stub_session_log(monkeypatch):
    """Replace append_transcript so it doesn't talk to a real Redis."""
    transcripts = []

    def _capture(sid, text):
        transcripts.append({"sid": sid, "text": text})

    monkeypatch.setattr(dispatch_mod, "append_transcript", _capture)
    return transcripts


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_dispatch_returns_200_with_reply_and_agent(
    client, stub_runner, stub_tts, stub_session_log
):
    resp = client.post(
        "/dispatch",
        json={"session_id": "sess-1", "message": "request startup"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "Cleared to LEPA"
    assert body["agent"] == "DEL"
    assert body["aircraft_registration"] == "EC-MIG"
    assert body["callsign"] == "IBE3421"
    assert body["session_id"] == "sess-1"


def test_dispatch_appends_transcript_before_orchestrator_call(
    client, stub_runner, stub_tts, stub_session_log
):
    client.post("/dispatch", json={"session_id": "sess-1", "message": "hello"})

    assert len(stub_session_log) == 1
    assert stub_session_log[0] == {"sid": "sess-1", "text": "hello"}
    # And the orchestrator did get called
    assert len(stub_runner.calls_list) == 1


def test_dispatch_publishes_tts_on_success(
    client, stub_runner, stub_tts, stub_session_log
):
    client.post("/dispatch", json={"session_id": "sess-1", "message": "hello"})

    tts_queue = stub_tts.lists["tts:queue"]
    assert len(tts_queue) == 1
    payload = json.loads(tts_queue[0])
    assert payload == {"text": "Cleared to LEPA"}


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_dispatch_returns_500_when_orchestrator_raises(
    client, stub_runner, stub_tts, stub_session_log
):
    stub_runner.raise_exception(RuntimeError("agent boom"))

    resp = client.post(
        "/dispatch", json={"session_id": "sess-1", "message": "hello"}
    )

    assert resp.status_code == 500
    assert "Orchestrator error" in resp.json()["detail"]


def test_dispatch_transcript_appended_even_when_orchestrator_raises(
    client, stub_runner, stub_tts, stub_session_log
):
    """Transcript capture happens BEFORE the orchestrator call -- must persist on failure."""
    stub_runner.raise_exception(RuntimeError("agent boom"))

    client.post("/dispatch", json={"session_id": "sess-1", "message": "msg"})

    assert len(stub_session_log) == 1
    assert stub_session_log[0]["text"] == "msg"


def test_dispatch_tts_failure_does_not_break_response(
    client, stub_runner, stub_session_log, monkeypatch, fake_redis
):
    """If TTS publish fails, the dispatch must still return 200."""
    import types

    fake_redis.fail_next("rpush", times=10)
    fake_redis_module = types.SimpleNamespace(
        from_url=lambda url, **kw: fake_redis,
        Redis=lambda *a, **kw: fake_redis,
    )
    monkeypatch.setattr(dispatch_mod, "_redis", fake_redis_module)

    resp = client.post(
        "/dispatch", json={"session_id": "sess-1", "message": "hello"}
    )

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_dispatch_request_validation_rejects_missing_message(client):
    resp = client.post("/dispatch", json={"session_id": "sess-1"})
    assert resp.status_code == 422


def test_dispatch_request_validation_rejects_missing_session_id(client):
    resp = client.post("/dispatch", json={"message": "hi"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


def test_dispatch_includes_callsign_in_response(
    client, stub_runner, stub_tts, stub_session_log
):
    stub_runner.set_result(
        {
            "reply": "ok",
            "dependency": "GND",
            "registration": "EC-MIG",
            "callsign": "IBE3421",
        }
    )
    resp = client.post("/dispatch", json={"session_id": "s", "message": "m"})
    assert resp.json()["callsign"] == "IBE3421"


def test_dispatch_handles_null_registration(
    client, stub_runner, stub_tts, stub_session_log
):
    """A response with registration=None must still serialise (validates DispatchResponse nullable)."""
    stub_runner.set_result(
        {
            "reply": "Sorry, I didn't catch that",
            "dependency": "DEL",
            "registration": None,
            "callsign": None,
        }
    )
    resp = client.post("/dispatch", json={"session_id": "s", "message": "m"})
    assert resp.status_code == 200
    assert resp.json()["aircraft_registration"] is None
    assert resp.json()["callsign"] is None
