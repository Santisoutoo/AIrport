import asyncio
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import litellm
from fastapi import HTTPException

from config import get_config
from core.corrections import correct_callsigns
from core.phonetics import normalize_phonetic
from prompts.llm_corrector import INVALID_OUTPUT_PATTERN, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_model: Any = None
_loaded_model_id: str = ""
_executor = ThreadPoolExecutor(max_workers=2)


def _get_backend(model_id: str) -> str:
    return "faster-whisper" if "faster-whisper" in model_id else "transformers"


def load_model() -> Any:
    global _model, _loaded_model_id
    cfg = get_config()

    if _model is not None and _loaded_model_id == cfg.HF_MODEL:
        return _model

    backend = _get_backend(cfg.HF_MODEL)
    logger.info("Loading model: %s  backend=%s  device=%s", cfg.HF_MODEL, backend, cfg.WHISPER_DEVICE)

    if backend == "faster-whisper":
        from faster_whisper import WhisperModel
        _model = WhisperModel(cfg.HF_MODEL, device=cfg.WHISPER_DEVICE, compute_type=cfg.WHISPER_COMPUTE_TYPE)
    else:
        import torch
        from transformers import pipeline
        device = 0 if cfg.WHISPER_DEVICE == "cuda" and torch.cuda.is_available() else -1
        _model = pipeline("automatic-speech-recognition", model=cfg.HF_MODEL, device=device)

    _loaded_model_id = cfg.HF_MODEL
    logger.info("Model ready: %s", cfg.HF_MODEL)
    return _model


# ---------- Whisper ----------

def _whisper_sync(audio_bytes: bytes, suffix: str) -> str:
    cfg = get_config()
    model = load_model()
    backend = _get_backend(cfg.HF_MODEL)

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        if backend == "faster-whisper":
            segments, _ = model.transcribe(tmp_path, language=cfg.WHISPER_LANGUAGE, beam_size=cfg.WHISPER_BEAM_SIZE)
            text = " ".join(s.text for s in segments).strip()
        else:
            result = model(tmp_path, generate_kwargs={"language": cfg.WHISPER_LANGUAGE})
            text = result.get("text", "").strip()
    finally:
        os.unlink(tmp_path)

    return correct_callsigns(normalize_phonetic(text))


# ---------- LLM correction ----------

async def _llm_correct(raw: str) -> str:
    if not raw:
        return raw

    cfg = get_config()
    try:
        response = await litellm.acompletion(
            model=cfg.get_litellm_model(),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": raw},
            ],
            temperature=0,
            max_tokens=256,
        )
        corrected = response.choices[0].message.content.strip()

        if INVALID_OUTPUT_PATTERN.search(corrected):
            logger.warning("LLM returned invalid output, falling back to raw: %s", corrected)
            return raw

        return corrected
    except Exception as exc:
        logger.warning("LLM correction failed, using raw transcription: %s", exc)
        return raw


# ---------- Public entry point ----------

async def transcribe(audio_bytes: bytes, filename: str) -> dict:
    """Returns {"raw": str, "corrected": str}"""
    suffix = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".webm"
    try:
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(_executor, _whisper_sync, audio_bytes, suffix)
        corrected = await _llm_correct(raw)
        return {"raw": raw, "corrected": corrected}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Transcription failed")
        raise HTTPException(status_code=500, detail=f"Transcription error: {exc}") from exc
