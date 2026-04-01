import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.connection import get_db
from runner import run_orchestrator_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dispatch", tags=["dispatch"])

_executor = ThreadPoolExecutor(max_workers=4)


class DispatchRequest(BaseModel):
    session_id: str
    message: str   # raw Whisper transcription


class DispatchResponse(BaseModel):
    session_id: str
    reply: str
    agent: str                          # DEL | GND | TWR
    aircraft_registration: str | None   # corrected callsign, if found


@router.post("", response_model=DispatchResponse)
async def dispatch(req: DispatchRequest, db: Session = Depends(get_db)):
    """
    Route a transcribed pilot message to the correct ATC agent.

    The LLM orchestrator agent:
      1. Retrieves known aircraft from PostgreSQL / flight-plan service / Redis.
      2. Identifies and corrects the callsign.
      3. Determines the correct controller (DB dependency or content fallback).
      4. Forwards the message to DEL / GND / TWR and returns the reply.
    """
    loop = asyncio.get_event_loop()

    try:
        result = await loop.run_in_executor(
            _executor,
            run_orchestrator_agent,
            req.session_id,
            req.message,
            db,
        )
    except Exception as exc:
        logger.error("Orchestrator agent failed: %s", exc)
        raise HTTPException(
            status_code=500, detail=f"Orchestrator error: {exc}") from exc

    return DispatchResponse(
        session_id=req.session_id,
        reply=result["reply"],
        agent=result["dependency"],
        aircraft_registration=result["registration"],
    )
