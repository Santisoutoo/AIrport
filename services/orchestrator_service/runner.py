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

_FLIGHT_PLAN_URL = os.environ.get("FLIGHT_PLAN_SERVICE_URL", "")
_REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
_REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))


# ---------------------------------------------------------------------------
# Pre-fetch helpers (run before the agent starts, in the sync thread)
# ---------------------------------------------------------------------------

def _fetch_known_aircraft(db: Session) -> list[dict[str, Any]]:
    """
    Collect all known aircraft from three sources and merge them.
    PostgreSQL is authoritative; flight_plan_service and Redis fill in the rest.
    For GND/TWR aircraft the full clearance record is included.
    """
    aircraft: dict[str, dict[str, Any]] = {}

    # 1. PostgreSQL — most authoritative
    try:
        rows = db.query(AircraftClearance).all()
        for row in rows:
            entry: dict[str, Any] = {
                "registration": row.aircraft_registration,
                "dependency": row.dependency,
                "source": "db",
            }
            # Include full clearance for GND/TWR so sub-agents have context
            if row.dependency != "DEL":
                entry.update({
                    "squawk": row.squawk,
                    "initial_altitude": row.initial_altitude,
                    "instrumental_departure": row.instrumental_departure,
                    "runway_in_use": row.runway_in_use,
                    "altimeter": row.altimeter,
                    "destination_icao": row.destination_icao,
                    "clearance_text": row.clearance_text,
                })
            aircraft[row.aircraft_registration] = entry
    except Exception as exc:
        logger.warning("[ORCH] DB query failed in pre-fetch: %s", exc)

    # 2. Flight plan service — filed but not yet cleared
    if _FLIGHT_PLAN_URL:
        try:
            resp = httpx.get(f"{_FLIGHT_PLAN_URL}/plans", timeout=5)
            if resp.status_code == 200:
                for plan in resp.json():
                    reg = plan.get("aircraft_registration")
                    if not reg:
                        continue
                    callsign = plan.get("callsign", reg)
                    if reg in aircraft:
                        # Merge callsign into DB-sourced entry (DB has no callsign column)
                        aircraft[reg]["callsign"] = callsign
                    else:
                        aircraft[reg] = {"registration": reg, "callsign": callsign, "dependency": "DEL", "source": "flight_plan"}
        except Exception as exc:
            logger.warning("[ORCH] flight_plan_service unavailable: %s", exc)

    # 3. Redis active set — aircraft with live position data; callsign lives in the state hash
    try:
        r = redis_lib.Redis(host=_REDIS_HOST, port=_REDIS_PORT, db=0, decode_responses=True)
        for reg in r.smembers("aircraft:active_set"):
            state_callsign = r.hget(f"aircraft:state:{reg}", "callsign") or None
            if reg not in aircraft:
                aircraft[reg] = {"registration": reg, "callsign": state_callsign, "dependency": "DEL", "source": "redis"}
            elif state_callsign and not aircraft[reg].get("callsign"):
                aircraft[reg]["callsign"] = state_callsign
    except Exception as exc:
        logger.warning("[ORCH] Redis unavailable: %s", exc)

    result = list(aircraft.values())
    logger.info("[ORCH] pre-fetch: %d aircraft known", len(result))
    return result


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

    session_service = InMemorySessionService()
    runner = Runner(agent=orch_agent, app_name=_APP_NAME, session_service=session_service)

    async def _run() -> dict[str, Any]:
        await session_service.create_session(
            app_name=_APP_NAME,
            user_id="pilot",
            session_id=session_id,
            state={
                "session_id": session_id,
                "raw_transcription": message,
                "known_aircraft": known_aircraft,
            },
        )

        final_text = ""
        async for event in runner.run_async(
            user_id="pilot",
            session_id=session_id,
            new_message=Content(role="user", parts=[Part(text=message)]),
        ):
            logger.debug("[ORCH] event: %s", event)
            if event.is_final_response() and event.content and event.content.parts:
                final_text = "".join(
                    p.text for p in event.content.parts if hasattr(p, "text")
                )

        session = await session_service.get_session(
            app_name=_APP_NAME, user_id="pilot", session_id=session_id
        )
        state = session.state or {}
        return {
            "reply": state.get("reply") or final_text,
            "dependency": state.get("dependency", "DEL"),
            "registration": state.get("registration"),
            "clearance_data": state.get("clearance_data"),
            "advance_registration_gnd": state.get("advance_registration_gnd"),
        }

    result = asyncio.run(_run())

    # Persist clearance to DB (sync, after the async agent run)
    clearance_data = result.get("clearance_data")
    registration = result.get("registration")
    if clearance_data and registration:
        try:
            cd = clearance_data
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
            # NOTE: do NOT advance to GND here.
            # The aircraft stays in DEL until the controller says
            # "contact ground on {freq}". The advance_to_gnd tool sets
            # state["advance_registration_gnd"] when it detects that phrase.
            logger.info("[ORCH] clearance persisted for %s — waiting for ground frequency release", registration)
        except Exception as exc:
            logger.error("[ORCH] failed to persist clearance: %s", exc)

    # Advance to GND only after controller says "contact ground on {freq}"
    advance_reg_gnd = result.get("advance_registration_gnd")
    if advance_reg_gnd:
        try:
            repo = ClearanceRepository(db)
            repo.update_dependency(advance_reg_gnd, "GND")
            logger.info("[ORCH] ground release — %s advanced to GND", advance_reg_gnd)
        except Exception as exc:
            logger.error("[ORCH] failed to advance %s to GND: %s", advance_reg_gnd, exc)

    # Advance to TWR only after controller releases with "contact tower on {freq}"
    advance_reg_twr = result.get("advance_registration_twr")
    if advance_reg_twr:
        try:
            repo = ClearanceRepository(db)
            repo.update_dependency(advance_reg_twr, "TWR")
            logger.info("[ORCH] released to TWR — %s advanced to TWR", advance_reg_twr)
        except Exception as exc:
            logger.error("[ORCH] failed to advance %s to TWR: %s", advance_reg_twr, exc)

    # Reverse handoff: an aircraft that just landed is released BACK to GND.
    advance_reg_gnd_arrival = result.get("advance_registration_gnd_arrival")
    if advance_reg_gnd_arrival:
        try:
            repo = ClearanceRepository(db)
            updated = repo.update_dependency(advance_reg_gnd_arrival, "GND")
            if not updated:
                # Arrivals may not have a DEL-phase clearance row yet — create one.
                repo.upsert(
                    registration=advance_reg_gnd_arrival,
                    session_id=session_id,
                    squawk=0,
                    initial_altitude=0,
                    instrumental_departure="",
                    runway_in_use="",
                    altimeter=0.0,
                    destination_icao="",
                    clearance_text="",
                    dependency="GND",
                )
            logger.info("[ORCH] arrival ground release — %s advanced to GND", advance_reg_gnd_arrival)
        except Exception as exc:
            logger.error("[ORCH] failed to reverse-advance %s to GND: %s", advance_reg_gnd_arrival, exc)

    registration = result["registration"]
    callsign = None
    if registration:
        aircraft = next((a for a in known_aircraft if a.get("registration") == registration), None)
        if aircraft:
            callsign = aircraft.get("callsign")

    return {
        "reply": result["reply"],
        "dependency": result["dependency"],
        "registration": registration,
        "callsign": callsign,
    }
