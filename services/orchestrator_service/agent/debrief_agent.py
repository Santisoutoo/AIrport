"""Call Gemini (Vertex AI) to generate the session debrief.

Uses the google-genai SDK directly instead of ADK because the debrief is
a one-shot structured-JSON request with no tools, no memory, no routing
— so the Agent/Runner stack is overkill.

The SDK is already a transitive dependency of google-adk, so no new
package is required.
"""

import json
import logging
import os
from typing import Optional

from google import genai
from google.genai import types

from agent.debrief_prompt import DEBRIEF_SYSTEM_PROMPT
from frequency_audit import render_audit_for_prompt, render_audit_markdown

logger = logging.getLogger(__name__)

_DEBRIEF_MODEL = os.getenv("DEBRIEF_MODEL") or os.getenv("AGENT_MODEL", "gemini-2.5-flash")


# JSON schema the model must conform to. Gemini's response_schema accepts
# types.Schema objects or equivalent dict. We keep it simple with dicts.
_DEBRIEF_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "overall_score": {"type": "INTEGER"},
        "categories": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "score": {"type": "INTEGER"},
                    "summary": {"type": "STRING"},
                    "examples": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "ts": {"type": "STRING"},
                                "quote": {"type": "STRING"},
                                "verdict": {"type": "STRING"},
                                "note": {"type": "STRING"},
                            },
                            "required": ["ts", "quote", "verdict", "note"],
                        },
                    },
                },
                "required": ["name", "score", "summary", "examples"],
            },
        },
        "strengths": {"type": "ARRAY", "items": {"type": "STRING"}},
        "improvements": {"type": "ARRAY", "items": {"type": "STRING"}},
        "instructor_summary": {"type": "STRING"},
    },
    "required": ["overall_score", "categories", "strengths", "improvements", "instructor_summary"],
}


_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        # The SDK picks up GOOGLE_GENAI_USE_VERTEXAI / GOOGLE_CLOUD_PROJECT /
        # GOOGLE_CLOUD_LOCATION / GOOGLE_APPLICATION_CREDENTIALS from env.
        _client = genai.Client()
    return _client


def generate_debrief(
    timeline: str,
    stats: dict,
    airport_icao: str = "",
    freq_audit: Optional[dict] = None,
) -> dict:
    """Send the timeline to Gemini and return the parsed JSON debrief.

    Raises on SDK/network errors and on output that cannot be parsed.
    """
    audit_block = render_audit_for_prompt(freq_audit or {})
    user_prompt = (
        f"AIRPORT: {airport_icao or 'UNKNOWN'}\n"
        f"SESSION STATS: {json.dumps(stats)}\n\n"
        + (f"{audit_block}\n\n" if audit_block else "")
        + "SESSION DATA (timeline, strictly chronological):\n"
        "---BEGIN---\n"
        f"{timeline}\n"
        "---END---\n"
    )

    client = _get_client()
    config = types.GenerateContentConfig(
        system_instruction=DEBRIEF_SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=_DEBRIEF_SCHEMA,
        temperature=0.4,
    )

    resp = client.models.generate_content(
        model=_DEBRIEF_MODEL,
        contents=user_prompt,
        config=config,
    )
    raw = resp.text or ""
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("[debrief] malformed JSON from model: %s | raw=%r", exc, raw[:500])
        raise


def render_markdown(debrief: dict, freq_audit: Optional[dict] = None) -> str:
    """Cheap, deterministic Markdown rendering for the HMI modal.

    The HMI could render the JSON itself; we ship a pre-formatted block
    so the UI doesn't need its own templating logic.
    """
    lines: list[str] = []
    lines.append(f"# Session debrief — overall score: **{debrief.get('overall_score', '?')}/100**\n")

    audit_section = render_audit_markdown(freq_audit or {})
    if audit_section:
        lines.append(audit_section)
        lines.append("")

    lines.append("## Categories\n")
    for cat in debrief.get("categories", []):
        name = str(cat.get("name", "")).title()
        score = cat.get("score", "?")
        summary = cat.get("summary", "").strip()
        lines.append(f"### {name} — {score}/10")
        if summary:
            lines.append(summary)
        examples = cat.get("examples") or []
        for ex in examples:
            ts = ex.get("ts", "--:--:--")
            verdict = (ex.get("verdict") or "").upper()
            quote = (ex.get("quote") or "").strip().replace("\n", " ")
            note = (ex.get("note") or "").strip()
            mark = "✔" if verdict == "GOOD" else "✘" if verdict == "BAD" else "·"
            lines.append(f'- {mark} **{ts}** — "{quote}"  \n  {note}')
        lines.append("")

    strengths = debrief.get("strengths") or []
    if strengths:
        lines.append("## Strengths")
        for s in strengths:
            lines.append(f"- {s}")
        lines.append("")

    improvements = debrief.get("improvements") or []
    if improvements:
        lines.append("## Improvements")
        for s in improvements:
            lines.append(f"- {s}")
        lines.append("")

    summary = (debrief.get("instructor_summary") or "").strip()
    if summary:
        lines.append("## Instructor summary")
        lines.append(summary)

    return "\n".join(lines).strip()
