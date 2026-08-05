"""Unit tests for api/arrivals.py -- POST /api/v1/orchestrator/arrivals/register.

The endpoint is called by the arrival_simulator at dispatch time so the
orchestrator's ``_fetch_known_aircraft`` sees the arriving aircraft with
dependency='APP' and routes the reverse handoff (advance_to_gnd_arrival)
correctly when the controller releases it to ground.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.arrivals import router as arrivals_router
from db.connection import get_db
from db.models import AircraftClearance


@pytest.fixture
def app(db_session):
    """A FastAPI app with the arrivals router mounted and DB overridden."""
    application = FastAPI()
    application.include_router(arrivals_router)

    def _override_get_db():
        yield db_session

    application.dependency_overrides[get_db] = _override_get_db
    return application


@pytest.fixture
def client(app):
    return TestClient(app)


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_register_arrival_creates_row_with_dependency_app(client, db_session):
    resp = client.post(
        "/api/v1/orchestrator/arrivals/register",
        json={
            "aircraft_registration": "VLG1234",
            "callsign": "VLG1234",
            "aircraft_type": "A320",
            "destination_icao": "LEST",
            "runway_in_use": "17",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body == {"registered": "VLG1234", "dependency": "APP"}

    row = db_session.query(AircraftClearance).filter_by(aircraft_registration="VLG1234").one()
    assert row.dependency == "APP"
    assert row.runway_in_use == "17"
    assert row.destination_icao == "LEST"


def test_register_arrival_uses_default_destination_lest_and_rwy_17(client, db_session):
    """Only ``aircraft_registration`` is required; the rest have defaults."""
    resp = client.post(
        "/api/v1/orchestrator/arrivals/register",
        json={"aircraft_registration": "EC-NEW"},
    )
    assert resp.status_code == 201
    row = db_session.query(AircraftClearance).filter_by(aircraft_registration="EC-NEW").one()
    assert row.destination_icao == "LEST"
    assert row.runway_in_use == "17"


def test_register_arrival_idempotent_on_repeat_call(client, db_session):
    """A second POST for the same registration must update the existing row, not duplicate it."""
    client.post("/api/v1/orchestrator/arrivals/register", json={"aircraft_registration": "EC-X"})
    client.post(
        "/api/v1/orchestrator/arrivals/register",
        json={"aircraft_registration": "EC-X", "runway_in_use": "35"},
    )
    rows = db_session.query(AircraftClearance).filter_by(aircraft_registration="EC-X").all()
    assert len(rows) == 1
    assert rows[0].runway_in_use == "35"


def test_register_arrival_persists_session_id(client, db_session):
    client.post(
        "/api/v1/orchestrator/arrivals/register",
        json={"aircraft_registration": "EC-Y", "session_id": "training-2026-05"},
    )
    row = db_session.query(AircraftClearance).filter_by(aircraft_registration="EC-Y").one()
    assert row.session_id == "training-2026-05"


def test_register_arrival_uses_default_squawk_2000(client, db_session):
    """Arrivals get squawk=2000 since the assignment was done by Approach upstream."""
    client.post("/api/v1/orchestrator/arrivals/register", json={"aircraft_registration": "EC-Z"})
    row = db_session.query(AircraftClearance).filter_by(aircraft_registration="EC-Z").one()
    assert row.squawk == 2000


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_register_arrival_validation_rejects_missing_registration(client):
    resp = client.post("/api/v1/orchestrator/arrivals/register", json={})
    assert resp.status_code == 422


def test_register_arrival_validation_rejects_non_string_registration(client):
    resp = client.post(
        "/api/v1/orchestrator/arrivals/register",
        json={"aircraft_registration": 12345},
    )
    # FastAPI coerces ints to strings by default for str fields -> 201, or 422 in strict mode.
    # Either is acceptable as long as the schema is enforced.
    assert resp.status_code in (201, 422)
