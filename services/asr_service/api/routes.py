import logging
import os

import httpx
from fastapi import APIRouter, Form, UploadFile, File

from . import transcribe_service
from core.config import get_settings, AVAILABLE_MODELS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/asr", tags=["asr"])

_ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "")


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/models")
def get_models():
    """Return the list of available ATC Whisper models for the UI selector."""
    cfg = get_settings()
    return {
        "active": cfg.hf_model,
        "models": AVAILABLE_MODELS,
    }


@router.get("/config")
def get_config():
    """Return current ASR configuration (read-only, sourced from environment)."""
    return get_settings().model_dump()


@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    session_id: str = Form(""),
):
    audio_bytes = await audio.read()
    filename = audio.filename or "audio.webm"
    content_type = (audio.content_type or "audio/webm").split(";")[0].strip()
    logger.info("[ASR] transcribe: %d bytes, file=%s, ct=%s", len(audio_bytes), filename, content_type)

    text = await transcribe_service.transcribe(audio_bytes, filename)

    # If orchestrator is configured, dispatch the transcription for agent routing
    if _ORCHESTRATOR_URL and text:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                dispatch_resp = await client.post(
                    f"{_ORCHESTRATOR_URL}/dispatch",
                    json={"session_id": session_id, "message": text},
                )
                dispatch_resp.raise_for_status()
                dispatch_data = dispatch_resp.json()
                return {
                    "text": text,
                    "reply": dispatch_data.get("reply", ""),
                    "agent": dispatch_data.get("agent", ""),
                    "aircraft_registration": dispatch_data.get("aircraft_registration"),
                }
        except Exception as exc:
            logger.warning("[ASR] dispatch failed: %s — returning transcription only", exc)

    return {"text": text}
