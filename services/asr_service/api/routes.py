import logging
import httpx
from fastapi import APIRouter, HTTPException, UploadFile, File

logger = logging.getLogger(__name__)

from . import transcribe_service
from .config_service import load as load_cfg, save as save_cfg
from .models import AsrConfig, DEFAULTS

router = APIRouter(prefix="/api/v1/asr", tags=["asr"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/config")
def get_config():
    return load_cfg()


@router.post("/config")
def post_config(cfg: AsrConfig):
    save_cfg(cfg)
    return {"success": True}


@router.get("/ollama/models")
async def ollama_models():
    cfg = load_cfg()
    ollama_url = cfg.get("ollama_url") or DEFAULTS["ollama_url"]
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{ollama_url}/api/tags")
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            return {"models": models}
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Cannot reach Ollama at {ollama_url}: {exc}",
        ) from exc


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    cfg = load_cfg()
    audio_bytes = await audio.read()
    filename = audio.filename or "audio.webm"
    # Strip codec parameters (e.g. "audio/webm;codecs=opus" → "audio/webm")
    content_type = (audio.content_type or "audio/webm").split(";")[0].strip()
    print(f"[ASR] transcribe: {len(audio_bytes)} bytes, file={filename}, ct={content_type}", flush=True)

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

    return {"text": text}
