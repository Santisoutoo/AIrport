"""Runs the routing agent and does the bookkeeping no LLM is trusted with.

Three phases, in this order:

1. **Pre-fetch** — merge every aircraft the system knows about from PostgreSQL,
   the flight plan service and Redis, so the agent never has to ask.
2. **Agent run** — one ADK session in its own event loop (`asyncio.run`,
   because a FastAPI handler is already inside one), driven to completion.
3. **Side effects** — persist the DEL clearance, apply the phase handoff the
   agent flagged, and resolve the callsign for the response.
"""

import asyncio
import logging
import os
from typing import Any

import httpx
import redis as redis_lib
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from sqlalchemy.orm import Session

from agent.agent import orch_agent
from db.models import AircraftClearance
from db.repository import ClearanceRepository

logger = logging.getLogger(__name__)

_APP_NAME = "airport_orchestrator"
_USER_ID = "pilot"

_FLIGHT_PLAN_URL = os.environ.get("FLIGHT_PLAN_SERVICE_URL", "")
_REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
_REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))

_FLIGHT_PLAN_TIMEOUT_S = 5

# Clearance columns that only make sense once an aircraft has left DEL. Sending
# them for a DEL aircraft would just be a row of Nones.
_POST_DEL_CLEARANCE_FIELDS = (
    "squawk",
    "initial_altitude",
    "instrumental_departure",
    "runway_in_use",
    "altimeter",
    "destination_icao",
    "clearance_text",
)

# The three phase handoffs, each flagged by its own state key. Tuple order is
# the order they are applied in.
#   (state key, target phase, create the row when missing, success log, error log)
_DEPENDENCY_ADVANCES = (
    (
        "advance_registration_gnd",
        "GND",
        True,
        "[ORCH] ground release — %s advanced to GND",
        "[ORCH] failed to advance %s to GND: %s",
    ),
    (
        "advance_registration_twr",
        "TWR",
        False,
        "[ORCH] released to TWR — %s advanced to TWR",
        "[ORCH] failed to advance %s to TWR: %s",
    ),
    (
        "advance_registration_gnd_arrival",
        "GND",
        True,
        "[ORCH] arrival ground release — %s advanced to GND",
        "[ORCH] failed to reverse-advance %s to GND: %s",
    ),
)


# ---------------------------------------------------------------------------
# Pre-fetch helpers (run before the agent starts, in the sync thread)
# ---------------------------------------------------------------------------


def _db_entry(row: AircraftClearance) -> dict[str, Any]:
    """One aircraft as PostgreSQL knows it — the authoritative phase."""
    entry: dict[str, Any] = {
        "registration": row.aircraft_registration,
        "dependency": row.dependency,
        "source": "db",
    }
    if row.dependency == "DEL":
        return entry
    # Include the full clearance for GND/TWR so sub-agents have context
    entry.update({field: getattr(row, field) for field in _POST_DEL_CLEARANCE_FIELDS})
    return entry


def _collect_from_db(aircraft: dict[str, dict[str, Any]], db: Session) -> None:
    """Source 1: PostgreSQL — most authoritative, it owns the phase."""
    try:
        for row in db.query(AircraftClearance).all():
            aircraft[row.aircraft_registration] = _db_entry(row)
    except Exception as exc:
        logger.warning("[ORCH] DB query failed in pre-fetch: %s", exc)


def _merge_plan(aircraft: dict[str, dict[str, Any]], plan: dict) -> None:
    reg = plan.get("aircraft_registration")
    if not reg:
        return
    callsign = plan.get("callsign", reg)
    if reg in aircraft:
        # Merge callsign into DB-sourced entry (DB has no callsign column)
        aircraft[reg]["callsign"] = callsign
        return
    aircraft[reg] = {
        "registration": reg,
        "callsign": callsign,
        "dependency": "DEL",
        "source": "flight_plan",
    }


def _collect_from_flight_plans(aircraft: dict[str, dict[str, Any]]) -> None:
    """Source 2: the flight plan service — filed but not yet cleared."""
    if not _FLIGHT_PLAN_URL:
        return
    try:
        resp = httpx.get(f"{_FLIGHT_PLAN_URL}/plans", timeout=_FLIGHT_PLAN_TIMEOUT_S)
        if resp.status_code != 200:
            return
        for plan in resp.json():
            _merge_plan(aircraft, plan)
    except Exception as exc:
        logger.warning("[ORCH] flight_plan_service unavailable: %s", exc)


def _merge_live_aircraft(aircraft: dict[str, dict[str, Any]], reg: str, state_callsign: str | None) -> None:
    if reg not in aircraft:
        aircraft[reg] = {
            "registration": reg,
            "callsign": state_callsign,
            "dependency": "DEL",
            "source": "redis",
        }
        return
    if state_callsign and not aircraft[reg].get("callsign"):
        aircraft[reg]["callsign"] = state_callsign


def _collect_from_redis(aircraft: dict[str, dict[str, Any]]) -> None:
    """Source 3: the Redis active set — aircraft alive in the sim right now.

    The callsign lives in the state hash, not in the set itself.
    """
    try:
        r = redis_lib.Redis(host=_REDIS_HOST, port=_REDIS_PORT, db=0, decode_responses=True)
        for reg in r.smembers("aircraft:active_set"):
            state_callsign = r.hget(f"aircraft:state:{reg}", "callsign") or None
            _merge_live_aircraft(aircraft, reg, state_callsign)
    except Exception as exc:
        logger.warning("[ORCH] Redis unavailable: %s", exc)


def _fetch_known_aircraft(db: Session) -> list[dict[str, Any]]:
    """
    Collect all known aircraft from three sources and merge them.
    PostgreSQL is authoritative; flight_plan_service and Redis fill in the rest.
    For GND/TWR aircraft the full clearance record is included.

    Every source degrades independently: an outage in one drops its
    contribution and logs, it never fails the dispatch.
    """
    aircraft: dict[str, dict[str, Any]] = {}
    _collect_from_db(aircraft, db)
    _collect_from_flight_plans(aircraft)
    _collect_from_redis(aircraft)

    result = list(aircraft.values())
    logger.info("[ORCH] pre-fetch: %d aircraft known", len(result))
    return result


# ---------------------------------------------------------------------------
# Agent invocation
# ---------------------------------------------------------------------------


async def _drain_events(runner: Runner, session_id: str, message: str) -> str:
    """Run the agent to completion, keeping the last final-response text.

    That text is only the fallback: when a tool ran, the reply the controller
    hears comes from session state instead.
    """
    final_text = ""
    async for event in runner.run_async(
        user_id=_USER_ID,
        session_id=session_id,
        new_message=Content(role="user", parts=[Part(text=message)]),
    ):
        logger.debug("[ORCH] event: %s", event)
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(p.text for p in event.content.parts if hasattr(p, "text"))
    return final_text


async def _read_agent_outcome(
    session_service: InMemorySessionService, session_id: str, final_text: str
) -> dict[str, Any]:
    """Everything the tools left behind in session state."""
    session = await session_service.get_session(app_name=_APP_NAME, user_id=_USER_ID, session_id=session_id)
    state = session.state or {}
    return {
        "reply": state.get("reply") or final_text,
        "dependency": state.get("dependency", "DEL"),
        "registration": state.get("registration"),
        "clearance_data": state.get("clearance_data"),
        # KNOWN BUG, preserved deliberately by this refactor: only the GND key
        # is forwarded. `advance_registration_twr` and
        # `advance_registration_gnd_arrival` are set by their tools but never
        # read here, so those two handoffs never reach the database. Covered by
        # two strict xfail tests in tests/unit/orchestrator/test_runner.py;
        # fixing it is a behaviour change and belongs in its own PR.
        "advance_registration_gnd": state.get("advance_registration_gnd"),
    }


def _invoke_agent(session_id: str, message: str, known_aircraft: list[dict[str, Any]]) -> dict[str, Any]:
    """Run one ADK session start to finish and return what it left in state.

    Opens its own event loop: the caller is a sync function running in a
    thread-pool executor precisely because a FastAPI handler is already inside
    a loop of its own.
    """
    session_service = InMemorySessionService()
    runner = Runner(agent=orch_agent, app_name=_APP_NAME, session_service=session_service)

    async def _run() -> dict[str, Any]:
        await session_service.create_session(
            app_name=_APP_NAME,
            user_id=_USER_ID,
            session_id=session_id,
            state={
                "session_id": session_id,
                "raw_transcription": message,
                "known_aircraft": known_aircraft,
            },
        )
        final_text = await _drain_events(runner, session_id, message)
        return await _read_agent_outcome(session_service, session_id, final_text)

    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# Side effects (sync, after the async agent run)
# ---------------------------------------------------------------------------


def _persist_clearance(db: Session, session_id: str, result: dict[str, Any]) -> None:
    """Write the DEL clearance fields the agent obtained.

    NOTE: this does NOT advance to GND. The aircraft stays in DEL until the
    controller says "contact ground on {freq}"; the advance_to_gnd tool sets
    state["advance_registration_gnd"] when it detects that phrase.
    """
    cd = result.get("clearance_data")
    registration = result.get("registration")
    if not (cd and registration):
        return
    try:
        repo = ClearanceRepository(db)
        repo.upsert(
            registration=cd.get("aircraft_registration", registration),
            session_id=session_id,
            squawk=cd.get("squawk", 2000),
            initial_altitude=cd.get("initial_altitude", 6000),
            instrumental_departure=cd.get("instrumental_departure", ""),
            runway_in_use=cd.get("runway_in_use", ""),
            altimeter=cd.get("altimeter", 1013.0),
            destination_icao=cd.get("destination_icao", ""),
            clearance_text=cd.get("clearance_text", ""),
        )
        logger.info(
            "[ORCH] clearance persisted for %s — waiting for ground frequency release",
            registration,
        )
    except Exception as exc:
        logger.error("[ORCH] failed to persist clearance: %s", exc)


def _advance_dependency(
    db: Session,
    session_id: str,
    registration: str,
    dependency: str,
    *,
    create_if_missing: bool,
    success_log: str,
    error_log: str,
) -> None:
    """Move one aircraft to another controller phase.

    ``create_if_missing`` is the safety net for aircraft with no clearance row
    yet — an arrival, or a departure the LLM handed off early — so the next
    message still routes to the right controller.
    """
    try:
        repo = ClearanceRepository(db)
        updated = repo.update_dependency(registration, dependency)
        if not updated and create_if_missing:
            repo.upsert(
                registration=registration,
                session_id=session_id,
                squawk=0,
                initial_altitude=0,
                instrumental_departure="",
                runway_in_use="",
                altimeter=0.0,
                destination_icao="",
                clearance_text="",
                dependency=dependency,
            )
        logger.info(success_log, registration)
    except Exception as exc:
        logger.error(error_log, registration, exc)


def _apply_dependency_advances(db: Session, session_id: str, result: dict[str, Any]) -> None:
    """Apply whichever handoff the agent flagged, if any.

    Only an explicit release phrase gets here — the handoff tools set exactly
    one of the three state keys when they fire.
    """
    for state_key, dependency, create_if_missing, success_log, error_log in _DEPENDENCY_ADVANCES:
        registration = result.get(state_key)
        if not registration:
            continue
        _advance_dependency(
            db,
            session_id,
            registration,
            dependency,
            create_if_missing=create_if_missing,
            success_log=success_log,
            error_log=error_log,
        )


def _callsign_for(known_aircraft: list[dict[str, Any]], registration: str | None) -> str | None:
    if not registration:
        return None
    aircraft = next((a for a in known_aircraft if a.get("registration") == registration), None)
    return aircraft.get("callsign") if aircraft else None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_orchestrator_agent(
    session_id: str,
    message: str,
    db: Session,
) -> dict[str, Any]:
    """
    Route a pilot message through the LLM orchestrator agent.

    Returns dict with keys: reply, dependency, registration.
    """
    known_aircraft = _fetch_known_aircraft(db)
    result = _invoke_agent(session_id, message, known_aircraft)

    _persist_clearance(db, session_id, result)
    _apply_dependency_advances(db, session_id, result)

    registration = result["registration"]
    return {
        "reply": result["reply"],
        "dependency": result["dependency"],
        "registration": registration,
        "callsign": _callsign_for(known_aircraft, registration),
    }
