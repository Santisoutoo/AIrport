"""LLM fallback for callsign / SID entity mapping.

When the deterministic postprocessing (core.postprocess) cannot confidently
resolve a spoken callsign or SID against the active session lists, this module
asks Gemini (Vertex AI) to map ONLY those entities onto the correct candidate.

Uses the google-genai SDK directly (same pattern as the orchestrator debrief
agent): the client picks up GOOGLE_GENAI_USE_VERTEXAI / GOOGLE_CLOUD_PROJECT /
GOOGLE_CLOUD_LOCATION from the environment. The SDK import lives inside the
functions so the module still imports where google-genai is not installed
(e.g. the CPU service image or a local dev box).

Contract: fail-open. Any error — missing package, missing credentials, timeout,
malformed output — returns (text, False), leaving the deterministic result
untouched.
"""

import json
import logging

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a strict normaliser of ATC (air traffic control) transcriptions. "
    "You are given a transcription plus the list of active callsigns and the "
    "list of expected SIDs for this session. Replace ONLY the callsign and/or "
    "the SID that were mis-transcribed with the correct candidate taken from "
    "those lists. Do not change, reorder, add or remove anything else: keep all "
    "other words, numbers, frequencies and punctuation exactly as they are. If "
    "no callsign or SID from the lists matches, return the text unchanged. "
    'Respond with JSON only: {"text": <corrected transcription>, '
    '"changed": <true if you replaced anything, otherwise false>}.'
)

_RESPONSE_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "text": {"type": "STRING"},
        "changed": {"type": "BOOLEAN"},
    },
    "required": ["text", "changed"],
}

_client = None  # lazy google.genai.Client


def _get_client():
    global _client
    if _client is None:
        from google import genai

        # The SDK reads GOOGLE_GENAI_USE_VERTEXAI / GOOGLE_CLOUD_PROJECT /
        # GOOGLE_CLOUD_LOCATION / GOOGLE_APPLICATION_CREDENTIALS from env.
        _client = genai.Client()
    return _client


def llm_map_entities(
    text: str,
    session_callsigns: list[str],
    session_sids: list[str],
    model: str,
    timeout_s: float = 8.0,
) -> tuple[str, bool]:
    """Ask the LLM to snap the callsign/SID onto the session candidates.

    Returns (possibly corrected text, applied). Fail-open: on any error the
    input text is returned with applied=False.
    """
    try:
        from google.genai import types

        client = _get_client()
        user_prompt = (
            f"Active callsigns: {session_callsigns or 'none'}\n"
            f"Expected SIDs: {session_sids or 'none'}\n"
            f"Transcription: {text}"
        )
        config = types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
            temperature=0.0,
            http_options=types.HttpOptions(timeout=int(timeout_s * 1000)),
        )
        resp = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=config,
        )
        data = json.loads(resp.text or "{}")
        new_text = data.get("text")
        changed = bool(data.get("changed", False))
        if not isinstance(new_text, str) or not new_text.strip():
            return text, False
        return new_text, changed
    except Exception as exc:  # fail-open: never break transcription on LLM issues
        logger.warning("[ASR][LLM] fallback unavailable (%s) — keeping deterministic result", exc)
        return text, False
