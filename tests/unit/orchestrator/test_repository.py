"""Unit tests for ClearanceRepository (services/orchestrator_service/db/repository.py).

Uses a per-test in-memory SQLite engine (see tests/fixtures/fake_db.py). The
PostgreSQL JSONB column is mapped to JSON via the patch in tests/conftest.py.
"""

from __future__ import annotations

import time

import pytest

from db.models import AircraftClearance
from db.repository import ClearanceRepository


# ---------------------------------------------------------------------------
# upsert()
# ---------------------------------------------------------------------------


def test_upsert_creates_new_record(clearance_repo, db_session):
    row = clearance_repo.upsert(
        registration="EC-MIG",
        session_id="s1",
        squawk=4321,
        initial_altitude=6000,
        instrumental_departure="VAR1A",
        runway_in_use="17",
        altimeter=1013.0,
        destination_icao="LEPA",
        clearance_text="cleared",
    )

    assert row.id is not None
    assert row.aircraft_registration == "EC-MIG"
    assert row.squawk == 4321
    assert row.dependency == "DEL"

    persisted = db_session.query(AircraftClearance).filter_by(aircraft_registration="EC-MIG").one()
    assert persisted.id == row.id


def test_upsert_updates_existing_record_preserving_id(clearance_repo):
    first = clearance_repo.upsert(
        registration="EC-MIG",
        session_id="s1",
        squawk=4321,
        initial_altitude=6000,
        instrumental_departure="VAR1A",
        runway_in_use="17",
        altimeter=1013.0,
        destination_icao="LEPA",
        clearance_text="first",
    )
    first_id = first.id
    first_cleared_at = first.cleared_at

    time.sleep(0.01)  # ensure updated_at advances

    second = clearance_repo.upsert(
        registration="EC-MIG",
        session_id="s1",
        squawk=5555,
        initial_altitude=8000,
        instrumental_departure="VAR2B",
        runway_in_use="35",
        altimeter=1010.0,
        destination_icao="LEBL",
        clearance_text="updated",
    )

    assert second.id == first_id, "primary key must be preserved across upserts"
    assert second.squawk == 5555
    assert second.runway_in_use == "35"
    assert second.updated_at >= first_cleared_at


def test_upsert_default_dependency_is_DEL(clearance_repo):
    row = clearance_repo.upsert(
        registration="EC-NEW",
        session_id="s2",
        squawk=2000,
        initial_altitude=4000,
        instrumental_departure="",
        runway_in_use="17",
        altimeter=1013.0,
        destination_icao="LEMD",
        clearance_text="",
    )
    assert row.dependency == "DEL"


def test_upsert_arrival_dependency_app(clearance_repo):
    row = clearance_repo.upsert(
        registration="VLG1234",
        session_id="s3",
        squawk=0,
        initial_altitude=0,
        instrumental_departure="",
        runway_in_use="17",
        altimeter=1013.0,
        destination_icao="LEST",
        clearance_text="",
        dependency="APP",
    )
    assert row.dependency == "APP"


def test_upsert_overwrites_dependency_on_subsequent_call(clearance_repo):
    """If a later upsert passes a different dependency, it must persist."""
    clearance_repo.upsert(
        registration="EC-MIG",
        session_id="s1",
        squawk=1,
        initial_altitude=1,
        instrumental_departure="",
        runway_in_use="17",
        altimeter=1013.0,
        destination_icao="LEPA",
        clearance_text="",
        dependency="DEL",
    )
    updated = clearance_repo.upsert(
        registration="EC-MIG",
        session_id="s1",
        squawk=1,
        initial_altitude=1,
        instrumental_departure="",
        runway_in_use="17",
        altimeter=1013.0,
        destination_icao="LEPA",
        clearance_text="",
        dependency="GND",
    )
    assert updated.dependency == "GND"


# ---------------------------------------------------------------------------
# get()
# ---------------------------------------------------------------------------


def test_get_returns_none_for_unknown_registration(clearance_repo):
    assert clearance_repo.get("UNKNOWN") is None


def test_get_returns_record_after_upsert(clearance_repo):
    clearance_repo.upsert(
        registration="EC-XYZ",
        session_id="s4",
        squawk=7777,
        initial_altitude=5000,
        instrumental_departure="ABC1A",
        runway_in_use="35",
        altimeter=1012.0,
        destination_icao="LEMD",
        clearance_text="hello",
    )
    found = clearance_repo.get("EC-XYZ")
    assert found is not None
    assert found.squawk == 7777
    assert found.runway_in_use == "35"


# ---------------------------------------------------------------------------
# update_dependency()
# ---------------------------------------------------------------------------


def test_update_dependency_returns_true_when_row_exists(clearance_repo):
    clearance_repo.upsert(
        registration="EC-MIG",
        session_id="s1",
        squawk=2000,
        initial_altitude=6000,
        instrumental_departure="VAR1A",
        runway_in_use="17",
        altimeter=1013.0,
        destination_icao="LEPA",
        clearance_text="",
    )
    assert clearance_repo.update_dependency("EC-MIG", "GND") is True

    after = clearance_repo.get("EC-MIG")
    assert after is not None
    assert after.dependency == "GND"


def test_update_dependency_returns_false_when_no_row(clearance_repo):
    """Critical: runner.py relies on this to detect 'no row → fallback upsert'."""
    assert clearance_repo.update_dependency("GHOST-AC", "GND") is False


def test_update_dependency_updates_updated_at(clearance_repo):
    initial = clearance_repo.upsert(
        registration="EC-MIG",
        session_id="s1",
        squawk=2000,
        initial_altitude=6000,
        instrumental_departure="VAR1A",
        runway_in_use="17",
        altimeter=1013.0,
        destination_icao="LEPA",
        clearance_text="",
    )
    initial_updated = initial.updated_at

    time.sleep(0.01)
    clearance_repo.update_dependency("EC-MIG", "TWR")

    after = clearance_repo.get("EC-MIG")
    assert after is not None
    assert after.updated_at >= initial_updated


def test_update_dependency_chained_through_full_departure_path(clearance_repo):
    """DEL → GND → TWR — the canonical departure ownership chain."""
    clearance_repo.upsert(
        registration="EC-MIG",
        session_id="s1",
        squawk=2000,
        initial_altitude=6000,
        instrumental_departure="VAR1A",
        runway_in_use="17",
        altimeter=1013.0,
        destination_icao="LEPA",
        clearance_text="",
    )
    assert clearance_repo.get("EC-MIG").dependency == "DEL"

    clearance_repo.update_dependency("EC-MIG", "GND")
    assert clearance_repo.get("EC-MIG").dependency == "GND"

    clearance_repo.update_dependency("EC-MIG", "TWR")
    assert clearance_repo.get("EC-MIG").dependency == "TWR"


def test_update_dependency_chained_through_arrival_path(clearance_repo):
    """APP → TWR → GND — the reverse handoff after landing."""
    clearance_repo.upsert(
        registration="VLG1234",
        session_id="s9",
        squawk=0,
        initial_altitude=0,
        instrumental_departure="",
        runway_in_use="17",
        altimeter=1013.0,
        destination_icao="LEST",
        clearance_text="",
        dependency="APP",
    )
    clearance_repo.update_dependency("VLG1234", "TWR")
    assert clearance_repo.get("VLG1234").dependency == "TWR"

    clearance_repo.update_dependency("VLG1234", "GND")
    assert clearance_repo.get("VLG1234").dependency == "GND"


# ---------------------------------------------------------------------------
# Repository instantiation
# ---------------------------------------------------------------------------


def test_repository_uses_provided_session(db_session):
    """ClearanceRepository must operate on the session it was given, not a global one."""
    repo = ClearanceRepository(db_session)
    repo.upsert(
        registration="EC-ABC",
        session_id="s",
        squawk=1234,
        initial_altitude=3000,
        instrumental_departure="",
        runway_in_use="17",
        altimeter=1013.0,
        destination_icao="LEPA",
        clearance_text="",
    )
    direct = db_session.query(AircraftClearance).filter_by(aircraft_registration="EC-ABC").one()
    assert direct.squawk == 1234
