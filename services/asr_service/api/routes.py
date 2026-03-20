import logging

from fastapi import APIRouter, UploadFile, File

from . import transcribe_service
from core.config import get_settings, AVAILABLE_MODELS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/asr", tags=["asr"])


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
async def transcribe(audio: UploadFile = File(...)):
    audio_bytes = await audio.read()
    filename = audio.filename or "audio.webm"
    content_type = (audio.content_type or "audio/webm").split(";")[0].strip()
    logger.info(
        "[ASR] transcribe: %d bytes  file=%s  ct=%s",
        len(audio_bytes), filename, content_type,
    )
    text = await transcribe_service.transcribe(audio_bytes, filename)
    return {"text": text}
