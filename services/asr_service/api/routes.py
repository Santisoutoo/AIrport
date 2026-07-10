import json
import logging
import os

import httpx
from fastapi import APIRouter, Form, UploadFile, File

from . import transcribe_service
from core.config import get_settings, AVAILABLE_MODELS
from core.postprocess import postprocess_transcription
from prompts.whisper_context import ATC_PROMPT

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


def _parse_list_field(raw: str | None) -> list[str]:
    """Parse a Form field that may be a JSON array (["A", "B"]) or a CSV string ("A,B")."""
    if not raw:
        return []
    raw = raw.strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if str(v).strip()]
        except json.JSONDecodeError:
            logger.warning("[ASR] could not parse '%s' as JSON list — falling back to CSV", raw)
    return [v.strip() for v in raw.split(",") if v.strip()]


def _build_initial_prompt(
    context_mode: str, session_callsigns: list[str], session_sids: list[str],
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
    session_id: str = Form(""),
    apply_corrections: bool = Form(True),
    use_initial_prompt: bool = Form(True),
    context_mode: str = Form("generic"),
    session_callsigns: str | None = Form(None),
    session_sids: str | None = Form(None),
):
    audio_bytes = await audio.read()
    filename = audio.filename or "audio.webm"
    content_type = (audio.content_type or "audio/webm").split(";")[0].strip()

    callsigns_list = _parse_list_field(session_callsigns)
    sids_list = _parse_list_field(session_sids)

    # use_initial_prompt=False keeps overriding everything (backward compatible
    # with the pre-existing flag); otherwise the prompt follows context_mode.
    initial_prompt = (
        _build_initial_prompt(context_mode, callsigns_list, sids_list)
        if use_initial_prompt else None
    )

    logger.info(
        "[ASR] transcribe: %d bytes, file=%s, ct=%s, corrections=%s, context_mode=%s",
        len(audio_bytes), filename, content_type, apply_corrections, context_mode,
    )

    raw_text, duration_s = await transcribe_service.transcribe_raw(
        audio_bytes, filename, initial_prompt=initial_prompt,
    )

    if apply_corrections:
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
        }
        final_text = raw_text

    cfg = get_settings()
    response: dict = {
        # "text" kept for backward compatibility with existing clients
        # (controller_hmi_service/static/js/ptt.js reads data.text).
        "text": final_text,
        "transcription": final_text,
        "raw_transcription": raw_text,
        "postprocess_steps": steps,
        "duration_s": duration_s,
        "model": cfg.hf_model,
        "context_mode": context_mode,
    }

    # If orchestrator is configured, dispatch the transcription for agent routing
    if _ORCHESTRATOR_URL and final_text:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                dispatch_resp = await client.post(
                    f"{_ORCHESTRATOR_URL}/dispatch",
                    json={"session_id": session_id, "message": final_text},
                )
                dispatch_resp.raise_for_status()
                dispatch_data = dispatch_resp.json()
                response.update({
                    "reply": dispatch_data.get("reply", ""),
                    "agent": dispatch_data.get("agent", ""),
                    "aircraft_registration": dispatch_data.get("aircraft_registration"),
                })
        except Exception as exc:
            logger.warning("[ASR] dispatch failed: %s — returning transcription only", exc)

    return response
