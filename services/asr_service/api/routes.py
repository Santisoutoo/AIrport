import logging
import os

import httpx
from fastapi import APIRouter, Form, HTTPException, UploadFile, File

from fastapi import APIRouter, UploadFile, File

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
    cfg = load_cfg()
    audio_bytes = await audio.read()
    filename = audio.filename or "audio.webm"
    content_type = (audio.content_type or "audio/webm").split(";")[0].strip()
    print(
        f"[ASR] transcribe: {len(audio_bytes)} bytes, file={filename}, ct={content_type}", flush=True)

    backend = cfg.get("backend", DEFAULTS["backend"])

    if backend == "ollama":
        text = await transcribe_service.via_ollama(
            audio_bytes, filename, content_type,
            model=cfg.get("ollama_model", DEFAULTS["ollama_model"]),
            ollama_url=cfg.get("ollama_url", DEFAULTS["ollama_url"]),
        )
    else:
        text = await transcribe_service.via_api(
            audio_bytes, filename, content_type,
            model=cfg.get("api_model", DEFAULTS["api_model"]),
            api_key=cfg.get("api_key", ""),
            base_url=cfg.get("api_base_url", DEFAULTS["api_base_url"]),
        )

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
            logger.warning(
                "[ASR] dispatch failed: %s — returning transcription only", exc)

    return {"text": text}
