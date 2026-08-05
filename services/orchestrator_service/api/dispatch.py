import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor

import redis as _redis
from db.connection import get_db
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from runner import run_orchestrator_agent
from session_log import append_transcript
from sqlalchemy.orm import Session

from config import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dispatch", tags=["dispatch"])

_executor = ThreadPoolExecutor(max_workers=4)


class DispatchRequest(BaseModel):
    session_id: str
    message: str  # raw Whisper transcription


class DispatchResponse(BaseModel):
    session_id: str
    reply: str
    agent: str  # DEL | GND | TWR
    aircraft_registration: str | None  # corrected callsign, if found
    callsign: str | None = None  # operational callsign (e.g. BAW5939); falls back to registration


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

    # Capture the controller transmission before dispatch so the debrief
    # has the exact text that arrived from ASR, even if the agent errors.
    append_transcript(req.session_id, req.message)

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
        raise HTTPException(status_code=500, detail=f"Orchestrator error: {exc}") from exc

    try:
        _r = _redis.from_url(
            f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}",
            decode_responses=True,
        )
        _r.rpush("tts:queue", json.dumps({"text": result["reply"]}))
    except Exception as _exc:
        logger.warning("TTS publish failed: %s", _exc)

    return DispatchResponse(
        session_id=req.session_id,
        reply=result["reply"],
        agent=result["dependency"],
        aircraft_registration=result["registration"],
        callsign=result.get("callsign"),
    )
