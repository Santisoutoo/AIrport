import logging

from fastapi import APIRouter, UploadFile, File

from . import transcribe_service
from config import get_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/transcription", tags=["transcription"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/config")
def get_cfg():
    cfg = get_config()
    return {
        "hf_model": cfg.HF_MODEL,
        "whisper_device": cfg.WHISPER_DEVICE,
        "agent_mode": cfg.AGENT_MODE,
        "llm_model": cfg.get_litellm_model(),
    }


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    audio_bytes = await audio.read()
    filename = audio.filename or "audio.webm"
    logger.info("[transcription] %d bytes  file=%s", len(audio_bytes), filename)
    result = await transcribe_service.transcribe(audio_bytes, filename)
    return result
