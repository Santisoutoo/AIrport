import logging
import os
import time

import httpx
from core.config import AVAILABLE_MODELS, get_settings
from core.llm_postprocess import llm_map_entities
from core.postprocess import FUZZY_THRESHOLD, postprocess_transcription
from fastapi import APIRouter, Depends, File, UploadFile
from prompts.whisper_context import ATC_PROMPT

from . import transcribe_service
from .schemas import TranscribeOptions

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


def _build_initial_prompt(
    context_mode: str,
    session_callsigns: list[str],
    session_sids: list[str],
) -> str | None:
    """Build the Whisper initial_prompt for the given context mode.

    - "none"    -> no prompt at all.
    - "generic" -> the existing ATC_PROMPT (default, backward compatible).
    - "session" -> ATC_PROMPT + active callsigns/SIDs for this session.
    """
    if context_mode == "none":
        return None
    if context_mode == "session":
        parts = [ATC_PROMPT]
        if session_callsigns:
            parts.append(f"Active callsigns: {', '.join(session_callsigns)}.")
        if session_sids:
            parts.append(f"Expected SIDs: {', '.join(session_sids)}.")
        return "\n".join(parts)
    return ATC_PROMPT  # "generic" or any unrecognised value


@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    options: TranscribeOptions = Depends(TranscribeOptions.as_form),
):
    audio_bytes = await audio.read()
    filename = audio.filename or "audio.webm"
    content_type = (audio.content_type or "audio/webm").split(";")[0].strip()

    callsigns_list = options.callsigns
    sids_list = options.sids

    # use_initial_prompt=False keeps overriding everything (backward compatible
    # with the pre-existing flag); otherwise the prompt follows context_mode.
    initial_prompt = (
        _build_initial_prompt(options.context_mode, callsigns_list, sids_list) if options.use_initial_prompt else None
    )

    logger.info(
        "[ASR] transcribe: %d bytes, file=%s, ct=%s, corrections=%s, context_mode=%s",
        len(audio_bytes),
        filename,
        content_type,
        options.apply_corrections,
        options.context_mode,
    )

    raw_text, duration_s = await transcribe_service.transcribe_raw(
        audio_bytes,
        filename,
        initial_prompt=initial_prompt,
    )

    cfg = get_settings()

    if options.apply_corrections:
        steps = postprocess_transcription(
            raw_text,
            session_callsigns=callsigns_list or None,
            session_sids=sids_list or None,
        )
        final_text = steps["final"]
    else:
        steps = {
            "after_number_norm": raw_text,
            "after_callsign_fix": raw_text,
            "final": raw_text,
            "cs_fuzzy_candidate": None,
            "cs_fuzzy_score": 0.0,
            "sid_fuzzy_candidate": None,
            "sid_fuzzy_score": 0.0,
            "cs_icao": None,
            "cs_unknown_airline": False,
        }
        final_text = raw_text

    # LLM fallback — only in session mode, when enabled, when we actually have
    # session lists AND the deterministic pass could not confidently resolve an
    # entity we have a list for (callsign, or SID if session SIDs were given).
    llm_enabled = cfg.llm_fallback if options.llm_fallback is None else options.llm_fallback
    cs_unresolved = bool(callsigns_list) and (
        steps["cs_fuzzy_candidate"] is None or steps["cs_fuzzy_score"] < FUZZY_THRESHOLD
    )
    sid_unresolved = bool(sids_list) and (
        steps["sid_fuzzy_candidate"] is None or steps["sid_fuzzy_score"] < FUZZY_THRESHOLD
    )
    deterministic_failed = cs_unresolved or sid_unresolved

    llm_applied = False
    llm_latency_s = 0.0
    if (
        options.apply_corrections
        and options.context_mode == "session"
        and llm_enabled
        and (callsigns_list or sids_list)
        and deterministic_failed
    ):
        t0 = time.perf_counter()
        llm_text, applied = llm_map_entities(
            final_text,
            callsigns_list,
            sids_list,
            cfg.llm_model,
        )
        llm_latency_s = time.perf_counter() - t0
        if applied and llm_text and llm_text != final_text:
            final_text = llm_text
            llm_applied = True

    response: dict = {
        # "text" kept for backward compatibility with existing clients
        # (controller_hmi_service/static/js/ptt.js reads data.text).
        "text": final_text,
        "transcription": final_text,
        "raw_transcription": raw_text,
        "postprocess_steps": steps,
        "duration_s": duration_s,
        "model": cfg.hf_model,
        "context_mode": options.context_mode,
        "llm_applied": llm_applied,
        "llm_latency_s": llm_latency_s,
    }

    # If orchestrator is configured, dispatch the transcription for agent routing
    if _ORCHESTRATOR_URL and final_text:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                dispatch_resp = await client.post(
                    f"{_ORCHESTRATOR_URL}/dispatch",
                    json={"session_id": options.session_id, "message": final_text},
                )
                dispatch_resp.raise_for_status()
                dispatch_data = dispatch_resp.json()
                response.update(
                    {
                        "reply": dispatch_data.get("reply", ""),
                        "agent": dispatch_data.get("agent", ""),
                        "aircraft_registration": dispatch_data.get("aircraft_registration"),
                    }
                )
        except Exception as exc:
            logger.warning("[ASR] dispatch failed: %s — returning transcription only", exc)

    return response
