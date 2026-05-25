"""Unit tests for services/orchestrator_service/runner.py.

Two surfaces are tested:

1. ``_fetch_known_aircraft`` -- merges PostgreSQL, flight_plan_service, and
   Redis into a single list of dicts, with graceful degradation when any
   source fails.
2. ``run_orchestrator_agent`` -- the public entry point that wraps the LLM
   call, persists clearance data, and applies dependency transitions.

The ADK Runner is replaced with ``FakeADKRunner`` (tests/fixtures/adk_runner.py)
which writes scripted state into the session before yielding a final event.
"""

from __future__ import annotations

import httpx
import pytest
import respx

import runner as runner_mod
from db.models import AircraftClearance
from tests.fixtures.adk_runner import install_fake_runner


# ---------------------------------------------------------------------------
# _fetch_known_aircraft
# ---------------------------------------------------------------------------


def _patch_redis(monkeypatch, fake_redis):
    """Make runner.redis_lib.Redis(...) return our FakeRedis."""
    import types

    fake_module = types.SimpleNamespace(
        Redis=lambda *a, **kw: fake_redis,
        from_url=lambda url, **kw: fake_redis,
    )
    monkeypatch.setattr(runner_mod, "redis_lib", fake_module)


def _patch_flight_plan_url(monkeypatch, url: str | None):
    monkeypatch.setattr(runner_mod, "_FLIGHT_PLAN_URL", url or "")


@respx.mock
def test_fetch_known_aircraft_db_only_returns_clearances(
    db_session, clearance_factory, fake_redis, monkeypatch
):
    clearance_factory(registration="EC-MIG", dependency="DEL")
    _patch_redis(monkeypatch, fake_redis)
    _patch_flight_plan_url(monkeypatch, None)

    result = runner_mod._fetch_known_aircraft(db_session)

    assert len(result) == 1
    assert result[0]["registration"] == "EC-MIG"
    assert result[0]["source"] == "db"


@respx.mock
def test_fetch_known_aircraft_includes_full_clearance_for_gnd(
    db_session, clearance_factory, fake_redis, monkeypatch
):
    clearance_factory(
        registration="EC-MIG",
        dependency="GND",
        squawk=4321,
        runway_in_use="17",
        instrumental_departure="VAR1A",
        destination_icao="LEPA",
    )
    _patch_redis(monkeypatch, fake_redis)
    _patch_flight_plan_url(monkeypatch, None)

    result = runner_mod._fetch_known_aircraft(db_session)
    entry = next(e for e in result if e["registration"] == "EC-MIG")

    # GND/TWR must include the full clearance bundle so the LLM has context
    assert entry["squawk"] == 4321
    assert entry["runway_in_use"] == "17"
    assert entry["instrumental_departure"] == "VAR1A"
    assert entry["destination_icao"] == "LEPA"


@respx.mock
def test_fetch_known_aircraft_DEL_entry_has_no_clearance_fields(
    db_session, clearance_factory, fake_redis, monkeypatch
):
    """For dependency='DEL' the clearance bundle is intentionally omitted."""
    clearance_factory(registration="EC-MIG", dependency="DEL", squawk=4321)
    _patch_redis(monkeypatch, fake_redis)
    _patch_flight_plan_url(monkeypatch, None)

    result = runner_mod._fetch_known_aircraft(db_session)
    entry = result[0]
    assert "squawk" not in entry
    assert "runway_in_use" not in entry


@respx.mock
def test_fetch_known_aircraft_merges_flight_plan_callsign_into_db_entry(
    db_session, clearance_factory, fake_redis, monkeypatch
):
    clearance_factory(registration="EC-MIG", dependency="DEL")
    respx.get("http://fp.test/plans").mock(
        return_value=httpx.Response(
            200, json=[{"aircraft_registration": "EC-MIG", "callsign": "IBE3421"}]
        )
    )
    _patch_redis(monkeypatch, fake_redis)
    _patch_flight_plan_url(monkeypatch, "http://fp.test")

    result = runner_mod._fetch_known_aircraft(db_session)
    entry = next(e for e in result if e["registration"] == "EC-MIG")

    assert entry["callsign"] == "IBE3421"
    assert entry["source"] == "db"  # source unchanged


@respx.mock
def test_fetch_known_aircraft_redis_adds_unknown_aircraft_as_del(
    db_session, fake_redis, monkeypatch
):
    """An aircraft present only in Redis (not in DB or flight_plan) becomes a DEL entry."""
    fake_redis.sadd("aircraft:active_set", "EC-NEW")
    fake_redis.hset("aircraft:state:EC-NEW", "callsign", "VLG7777")
    _patch_redis(monkeypatch, fake_redis)
    _patch_flight_plan_url(monkeypatch, None)

    result = runner_mod._fetch_known_aircraft(db_session)
    entry = next(e for e in result if e["registration"] == "EC-NEW")

    assert entry["dependency"] == "DEL"
    assert entry["source"] == "redis"
    assert entry["callsign"] == "VLG7777"


@respx.mock
def test_fetch_known_aircraft_redis_fills_missing_callsign_for_db_entry(
    db_session, clearance_factory, fake_redis, monkeypatch
):
    """DB entry has no callsign and flight_plan is offline -> Redis state hash fills it in."""
    clearance_factory(registration="EC-MIG", dependency="DEL")
    fake_redis.sadd("aircraft:active_set", "EC-MIG")
    fake_redis.hset("aircraft:state:EC-MIG", "callsign", "IBE3421")
    _patch_redis(monkeypatch, fake_redis)
    _patch_flight_plan_url(monkeypatch, None)

    result = runner_mod._fetch_known_aircraft(db_session)
    entry = next(e for e in result if e["registration"] == "EC-MIG")

    assert entry["callsign"] == "IBE3421"


@respx.mock
def test_fetch_known_aircraft_redis_failure_does_not_crash(
    db_session, clearance_factory, fake_redis, monkeypatch
):
    clearance_factory(registration="EC-MIG", dependency="DEL")
    fake_redis.fail_next("smembers", times=10)
    _patch_redis(monkeypatch, fake_redis)
    _patch_flight_plan_url(monkeypatch, None)

    # Must not raise
    result = runner_mod._fetch_known_aircraft(db_session)
    assert len(result) == 1
    assert result[0]["registration"] == "EC-MIG"


@respx.mock
def test_fetch_known_aircraft_flight_plan_503_falls_through(
    db_session, clearance_factory, fake_redis, monkeypatch
):
    clearance_factory(registration="EC-MIG", dependency="DEL")
    respx.get("http://fp.test/plans").mock(return_value=httpx.Response(503))
    _patch_redis(monkeypatch, fake_redis)
    _patch_flight_plan_url(monkeypatch, "http://fp.test")

    result = runner_mod._fetch_known_aircraft(db_session)
    # No callsign was injected from FP (since 503), but DB row is intact
    assert len(result) == 1
    assert result[0]["registration"] == "EC-MIG"


# ---------------------------------------------------------------------------
# run_orchestrator_agent -- persistence + dependency advances
# ---------------------------------------------------------------------------


@respx.mock
def test_run_orchestrator_agent_persists_clearance_when_data_present(
    db_session, fake_redis, monkeypatch
):
    _patch_redis(monkeypatch, fake_redis)
    _patch_flight_plan_url(monkeypatch, None)

    fake = install_fake_runner(monkeypatch, runner_mod)
    fake.script(
        state_updates={
            "reply": "Cleared to LEPA",
            "dependency": "DEL",
            "registration": "EC-MIG",
            "clearance_data": {
                "squawk": 4321,
                "initial_altitude": 6000,
                "instrumental_departure": "VAR1A",
                "runway_in_use": "17",
                "altimeter": 1013.0,
                "destination_icao": "LEPA",
                "clearance_text": "Cleared to LEPA",
            },
        },
        final_text="Cleared to LEPA",
    )

    result = runner_mod.run_orchestrator_agent("sess-1", "request startup", db_session)

    assert result["reply"] == "Cleared to LEPA"
    assert result["dependency"] == "DEL"
    assert result["registration"] == "EC-MIG"

    row = db_session.query(AircraftClearance).filter_by(aircraft_registration="EC-MIG").one()
    assert row.squawk == 4321
    assert row.runway_in_use == "17"
    assert row.dependency == "DEL"


@respx.mock
def test_run_orchestrator_agent_uses_fallback_squawk_when_clearance_missing_fields(
    db_session, fake_redis, monkeypatch
):
    """When clearance_data only carries partial fields, the unspecified ones
    must fall back to the runner-side defaults (squawk=2000, alt=6000, etc).

    Note: an *empty* dict is falsy and skips persistence entirely -- only a
    non-empty clearance_data triggers the upsert.
    """
    _patch_redis(monkeypatch, fake_redis)
    _patch_flight_plan_url(monkeypatch, None)

    fake = install_fake_runner(monkeypatch, runner_mod)
    fake.script(
        state_updates={
            "reply": "ok",
            "dependency": "DEL",
            "registration": "EC-MIG",
            # Only `clearance_text` is set -- everything else takes runner defaults.
            "clearance_data": {"clearance_text": "Cleared to LEPA"},
        },
        final_text="ok",
    )

    runner_mod.run_orchestrator_agent("sess-1", "msg", db_session)

    row = db_session.query(AircraftClearance).filter_by(aircraft_registration="EC-MIG").one()
    # Defaults defined in runner.py
    assert row.squawk == 2000
    assert row.initial_altitude == 6000
    assert row.altimeter == 1013.0
    assert row.clearance_text == "Cleared to LEPA"


@respx.mock
def test_run_orchestrator_agent_advances_to_gnd_when_flag_set(
    db_session, clearance_factory, fake_redis, monkeypatch
):
    """advance_registration_gnd in state must flip the row to dependency='GND'."""
    clearance_factory(registration="EC-MIG", dependency="DEL")
    _patch_redis(monkeypatch, fake_redis)
    _patch_flight_plan_url(monkeypatch, None)

    fake = install_fake_runner(monkeypatch, runner_mod)
    fake.script(
        state_updates={
            "reply": "121.9, IBE3421",
            "dependency": "GND",
            "registration": "EC-MIG",
            "advance_registration_gnd": "EC-MIG",
        },
        final_text="121.9, IBE3421",
    )

    runner_mod.run_orchestrator_agent("sess-1", "contact ground 121.9", db_session)

    row = db_session.query(AircraftClearance).filter_by(aircraft_registration="EC-MIG").one()
    assert row.dependency == "GND"


@pytest.mark.xfail(
    reason=(
        "runner.py:144-150 only includes `advance_registration_gnd` in the dict "
        "returned by the inner _run() coroutine -- `advance_registration_twr` and "
        "`advance_registration_gnd_arrival` are missing, so the post-run dependency "
        "advance to TWR/GND-arrival never fires. Documented in memoria 5.3.3 as a "
        "real bug surfaced by the test battery."
    ),
    strict=True,
)
@respx.mock
def test_run_orchestrator_agent_advances_to_twr(
    db_session, clearance_factory, fake_redis, monkeypatch
):
    clearance_factory(registration="EC-MIG", dependency="GND")
    _patch_redis(monkeypatch, fake_redis)
    _patch_flight_plan_url(monkeypatch, None)

    fake = install_fake_runner(monkeypatch, runner_mod)
    fake.script(
        state_updates={
            "reply": "118.3, IBE3421",
            "dependency": "TWR",
            "registration": "EC-MIG",
            "advance_registration_twr": "EC-MIG",
        },
        final_text="118.3, IBE3421",
    )

    runner_mod.run_orchestrator_agent("sess-1", "contact tower 118.3", db_session)

    row = db_session.query(AircraftClearance).filter_by(aircraft_registration="EC-MIG").one()
    assert row.dependency == "TWR"


@pytest.mark.xfail(
    reason=(
        "Same bug as advance_to_twr: runner.py's inner _run() does not pass "
        "`advance_registration_gnd_arrival` through to the outer scope, so the "
        "reverse-handoff upsert is never executed. Documented in memoria 5.3.3."
    ),
    strict=True,
)
@respx.mock
def test_run_orchestrator_agent_arrival_advance_to_gnd_creates_row_if_missing(
    db_session, fake_redis, monkeypatch
):
    """The reverse-handoff fallback: if no row exists yet, upsert with dependency='GND'."""
    _patch_redis(monkeypatch, fake_redis)
    _patch_flight_plan_url(monkeypatch, None)

    fake = install_fake_runner(monkeypatch, runner_mod)
    fake.script(
        state_updates={
            "reply": "121.9, VLG1234",
            "dependency": "GND",
            "registration": "EC-NEW",
            "advance_registration_gnd_arrival": "EC-NEW",
        },
        final_text="121.9, VLG1234",
    )

    runner_mod.run_orchestrator_agent("sess-1", "contact ground", db_session)

    row = (
        db_session.query(AircraftClearance)
        .filter_by(aircraft_registration="EC-NEW")
        .one_or_none()
    )
    assert row is not None
    assert row.dependency == "GND"


@respx.mock
def test_run_orchestrator_agent_returns_callsign_from_known_aircraft(
    db_session, clearance_factory, fake_redis, monkeypatch
):
    clearance_factory(registration="EC-MIG", dependency="DEL")
    fake_redis.sadd("aircraft:active_set", "EC-MIG")
    fake_redis.hset("aircraft:state:EC-MIG", "callsign", "IBE3421")
    _patch_redis(monkeypatch, fake_redis)
    _patch_flight_plan_url(monkeypatch, None)

    fake = install_fake_runner(monkeypatch, runner_mod)
    fake.script(
        state_updates={"reply": "ok", "dependency": "DEL", "registration": "EC-MIG"},
        final_text="ok",
    )

    result = runner_mod.run_orchestrator_agent("sess-1", "msg", db_session)

    assert result["callsign"] == "IBE3421"


@respx.mock
def test_run_orchestrator_agent_returns_null_callsign_when_no_registration(
    db_session, fake_redis, monkeypatch
):
    """If the agent didn't resolve a registration, callsign is None."""
    _patch_redis(monkeypatch, fake_redis)
    _patch_flight_plan_url(monkeypatch, None)

    fake = install_fake_runner(monkeypatch, runner_mod)
    fake.script(
        state_updates={"reply": "Sorry, I didn't catch that", "dependency": "DEL"},
        final_text="Sorry",
    )

    result = runner_mod.run_orchestrator_agent("sess-1", "garbled", db_session)
    assert result["callsign"] is None
    assert result["registration"] is None


@respx.mock
def test_run_orchestrator_agent_falls_back_to_final_text_when_state_reply_missing(
    db_session, fake_redis, monkeypatch
):
    """If the agent ends without setting state['reply'], the final event text is used."""
    _patch_redis(monkeypatch, fake_redis)
    _patch_flight_plan_url(monkeypatch, None)

    fake = install_fake_runner(monkeypatch, runner_mod)
    fake.script(state_updates={"dependency": "DEL"}, final_text="LLM raw output")

    result = runner_mod.run_orchestrator_agent("sess-1", "msg", db_session)
    assert result["reply"] == "LLM raw output"


@respx.mock
def test_run_orchestrator_agent_handles_upsert_exception_gracefully(
    db_session, fake_redis, monkeypatch
):
    """A persistence failure during clearance upsert must not crash the request."""
    _patch_redis(monkeypatch, fake_redis)
    _patch_flight_plan_url(monkeypatch, None)

    fake = install_fake_runner(monkeypatch, runner_mod)
    fake.script(
        state_updates={
            "reply": "ok",
            "dependency": "DEL",
            "registration": "EC-MIG",
            "clearance_data": {"squawk": 4321},
        },
        final_text="ok",
    )

    # Force ClearanceRepository.upsert to crash on first call
    from db import repository

    original = repository.ClearanceRepository.upsert
    calls = {"n": 0}

    def _raising_upsert(self, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("DB write failure")
        return original(self, **kwargs)

    monkeypatch.setattr(repository.ClearanceRepository, "upsert", _raising_upsert)

    # Must not raise
    result = runner_mod.run_orchestrator_agent("sess-1", "msg", db_session)
    assert result["reply"] == "ok"
