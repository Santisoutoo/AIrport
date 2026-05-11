"""Generate a session debrief: aggregate captured evidence, call Gemini,
return JSON + Markdown."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agent.debrief_agent import generate_debrief, render_markdown
from db.connection import get_db
from db.models import AircraftClearance
from debrief_builder import build_timeline, summarise_stats, truncate_timeline
from frequency_audit import audit_frequencies
from session_log import get_agent_replies, get_events, get_transcripts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debrief", tags=["debrief"])

_executor = ThreadPoolExecutor(max_workers=2)

_MIN_TRANSCRIPTS = 1  # sessions with nothing spoken are not evaluated


class DebriefRequest(BaseModel):
    session_id: str
    airport_icao: str | None = None


class DebriefResponse(BaseModel):
    session_id: str
    too_short: bool
    markdown: str
    debrief: dict | None = None
    stats: dict


def _load_com_frequencies() -> list[dict]:
    """Best-effort fetch of the active airport's COM frequencies from Redis.

    Returns [] on any failure so the audit cleanly falls back to defaults.
    """
    try:
        from shared.services.airport_data_store import AirportDataStore
        return AirportDataStore().get_com_frequencies() or []
    except Exception as exc:
        logger.warning("[debrief] could not load COM frequencies: %s", exc)
        return []


def _load_clearances(db: Session, session_id: str) -> list[dict]:
    rows = (
        db.query(AircraftClearance)
        .filter(AircraftClearance.session_id == session_id)
        .order_by(AircraftClearance.updated_at.asc())
        .all()
    )
    out: list[dict] = []
    for r in rows:
        out.append({
            "aircraft_registration": r.aircraft_registration,
            "dependency": r.dependency,
            "squawk": r.squawk,
            "initial_altitude": r.initial_altitude,
            "instrumental_departure": r.instrumental_departure,
            "runway_in_use": r.runway_in_use,
            "destination_icao": r.destination_icao,
            "clearance_text": r.clearance_text,
            "updated_at": r.updated_at.timestamp() if r.updated_at else None,
            "cleared_at": r.cleared_at.timestamp() if r.cleared_at else None,
        })
    return out


@router.post("/generate", response_model=DebriefResponse)
async def generate(req: DebriefRequest, db: Session = Depends(get_db)):
    sid = req.session_id.strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")

    transcripts = get_transcripts(sid)
    agent_replies = get_agent_replies(sid)
    events = get_events(sid)
    clearances = _load_clearances(db, sid)

    stats = summarise_stats(transcripts, agent_replies, events, clearances)
    freq_audit = audit_frequencies(transcripts, _load_com_frequencies())

    if len(transcripts) < _MIN_TRANSCRIPTS:
        return DebriefResponse(
            session_id=sid,
            too_short=True,
            markdown="# Session debrief\n\nSession too short to evaluate — no controller transmissions were captured.",
            debrief=None,
            stats=stats,
        )

    timeline = build_timeline(transcripts, agent_replies, events, clearances)
    timeline = truncate_timeline(timeline)

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            _executor,
            generate_debrief,
            timeline,
            stats,
            req.airport_icao or "",
            freq_audit,
        )
    except Exception as exc:
        logger.exception("[debrief] LLM call failed")
        raise HTTPException(status_code=502, detail=f"Debrief LLM error: {exc}") from exc

    try:
        markdown = render_markdown(result, freq_audit)
    except Exception as exc:
        logger.exception("[debrief] markdown render failed")
        markdown = f"# Session debrief\n\n```json\n{result}\n```"

    return DebriefResponse(
        session_id=sid,
        too_short=False,
        markdown=markdown,
        debrief=result,
        stats=stats,
    )
