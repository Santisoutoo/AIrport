import asyncio
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import HTTPException

from core.config import get_settings, get_model_backend
from core.phonetics import normalize_phonetic
from core.corrections import correct_callsigns
from prompts.whisper_context import ATC_PROMPT

logger = logging.getLogger(__name__)

_model: Any = None           # faster_whisper.WhisperModel  OR  transformers pipeline
_loaded_model_id: str = ""   # track which model is currently loaded
_executor = ThreadPoolExecutor(max_workers=2)


def load_model() -> Any:
    """Load (or return cached) the configured ATC Whisper model."""
    global _model, _loaded_model_id
    cfg = get_settings()

    if _model is not None and _loaded_model_id == cfg.hf_model:
        return _model

    backend = get_model_backend(cfg.hf_model)
    logger.info(
        "Loading model: %s  backend=%s  device=%s",
        cfg.hf_model, backend, cfg.whisper_device,
    )

    if backend == "faster-whisper":
        from faster_whisper import WhisperModel
        _model = WhisperModel(
            cfg.hf_model,
            device=cfg.whisper_device,
            compute_type=cfg.whisper_compute_type,
        )
    else:  # transformers pipeline (large-v3 etc.)
        import torch
        from transformers import pipeline
        device = 0 if cfg.whisper_device == "cuda" and torch.cuda.is_available() else -1
        _model = pipeline(
            "automatic-speech-recognition",
            model=cfg.hf_model,
            device=device,
        )

    _loaded_model_id = cfg.hf_model
    logger.info("Model ready: %s", cfg.hf_model)
    return _model


# ---------------------------------------------------------------------------
# Sync helpers (run in thread pool so the event loop stays free)
# ---------------------------------------------------------------------------

def _transcribe_faster_whisper(audio_bytes: bytes, suffix: str) -> str:
    cfg = get_settings()
    model = load_model()

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        segments, _ = model.transcribe(
            tmp_path,
            language=cfg.whisper_language,
            beam_size=cfg.whisper_beam_size,
            initial_prompt=ATC_PROMPT,
            condition_on_previous_text=False,
            hallucination_silence_threshold=2.0,
            no_speech_threshold=0.6,
        )
        text = " ".join(s.text for s in segments).strip()
    finally:
        os.unlink(tmp_path)

    return text


def _transcribe_transformers(audio_bytes: bytes, suffix: str) -> str:
    cfg = get_settings()
    pipe = load_model()

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        result = pipe(
            tmp_path,
            generate_kwargs={"language": cfg.whisper_language},
        )
        text = result.get("text", "").strip()
    finally:
        os.unlink(tmp_path)

    return text


def _transcribe_sync(audio_bytes: bytes, suffix: str) -> str:
    cfg = get_settings()
    backend = get_model_backend(cfg.hf_model)

    if backend == "faster-whisper":
        raw = _transcribe_faster_whisper(audio_bytes, suffix)
    else:
        raw = _transcribe_transformers(audio_bytes, suffix)

    return correct_callsigns(normalize_phonetic(raw))


# ---------------------------------------------------------------------------
# Public async entry point
# ---------------------------------------------------------------------------

async def transcribe(audio_bytes: bytes, filename: str) -> str:
    """Async wrapper — offloads CPU-bound inference to thread pool."""
    suffix = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".webm"
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _transcribe_sync, audio_bytes, suffix)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Transcription failed")
        raise HTTPException(status_code=500, detail=f"Transcription error: {exc}") from exc
