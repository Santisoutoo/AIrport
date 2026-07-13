import asyncio
import logging
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import HTTPException

from core.config import get_settings, get_model_backend

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
        on_gpu = cfg.whisper_device == "cuda" and torch.cuda.is_available()
        device = 0 if on_gpu else -1
        pipe_kwargs: dict = {}
        if on_gpu:
            # fp16 on GPU halves memory / speeds up inference; CPU stays fp32.
            pipe_kwargs["torch_dtype"] = torch.float16
        _model = pipeline(
            "automatic-speech-recognition",
            model=cfg.hf_model,
            device=device,
            **pipe_kwargs,
        )

    _loaded_model_id = cfg.hf_model
    logger.info("Model ready: %s", cfg.hf_model)
    return _model


# ---------------------------------------------------------------------------
# Sync helpers (run in thread pool so the event loop stays free)
#
# Each returns (raw_text, duration_s) where duration_s is ONLY the model
# inference time — measured with time.perf_counter() around the model call,
# excluding tempfile I/O and postprocessing (done by the caller).
# ---------------------------------------------------------------------------

def _transcribe_faster_whisper(
    audio_bytes: bytes, suffix: str, initial_prompt: str | None,
) -> tuple[str, float]:
    cfg = get_settings()
    model = load_model()

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        t0 = time.perf_counter()
        segments, _ = model.transcribe(
            tmp_path,
            language=cfg.whisper_language,
            beam_size=cfg.whisper_beam_size,
            initial_prompt=initial_prompt,
            condition_on_previous_text=False,
            hallucination_silence_threshold=2.0,
            no_speech_threshold=0.6,
        )
        text = " ".join(s.text for s in segments).strip()  # consumes the generator -> inference happens here
        duration_s = time.perf_counter() - t0
    finally:
        os.unlink(tmp_path)

    return text, duration_s


def _transcribe_transformers(
    audio_bytes: bytes, suffix: str, initial_prompt: str | None,
) -> tuple[str, float]:
    cfg = get_settings()
    pipe = load_model()

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    base_kwargs: dict = {"language": cfg.whisper_language}
    prompt_ids = None
    if initial_prompt:
        try:
            prompt_ids = pipe.tokenizer.get_prompt_ids(initial_prompt, return_tensors="pt")
        except Exception as exc:
            logger.warning(
                "[ASR] could not build prompt_ids for this transformers version (%s) — "
                "transcribing without initial prompt.", exc,
            )

    try:
        try:
            kwargs = dict(base_kwargs)
            if prompt_ids is not None:
                kwargs["prompt_ids"] = prompt_ids
            t0 = time.perf_counter()
            result = pipe(tmp_path, generate_kwargs=kwargs)
            duration_s = time.perf_counter() - t0
        except Exception as exc:
            if prompt_ids is None:
                raise
            logger.warning(
                "[ASR] transcription with initial_prompt failed (%s) — retrying without it.", exc,
            )
            t0 = time.perf_counter()
            result = pipe(tmp_path, generate_kwargs=base_kwargs)
            duration_s = time.perf_counter() - t0
        text = result.get("text", "").strip()
    finally:
        os.unlink(tmp_path)

    return text, duration_s


def _transcribe_sync(
    audio_bytes: bytes,
    suffix: str,
    initial_prompt: str | None,
) -> tuple[str, float]:
    cfg = get_settings()
    backend = get_model_backend(cfg.hf_model)

    if backend == "faster-whisper":
        return _transcribe_faster_whisper(audio_bytes, suffix, initial_prompt)
    return _transcribe_transformers(audio_bytes, suffix, initial_prompt)


# ---------------------------------------------------------------------------
# Public async entry point
# ---------------------------------------------------------------------------

async def transcribe_raw(
    audio_bytes: bytes,
    filename: str,
    initial_prompt: str | None = None,
) -> tuple[str, float]:
    """Async wrapper — offloads CPU-bound inference to thread pool.

    Returns (raw_text, duration_s). Postprocessing (number/callsign/SID
    correction) is applied by the caller (see api/routes.py + core/postprocess.py),
    NOT here, so duration_s reflects model inference only.
    """
    suffix = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".webm"
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            _transcribe_sync,
            audio_bytes,
            suffix,
            initial_prompt,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Transcription failed")
        raise HTTPException(status_code=500, detail=f"Transcription error: {exc}") from exc
