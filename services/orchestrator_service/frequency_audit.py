"""Deterministic audit of the frequencies the controller dictated during a session.

Pure functions, no I/O — the debrief endpoint loads transcripts and the
airport's COM frequencies from Redis, and hands both to `audit_frequencies`.
The result is fed to the debrief LLM as ground truth and surfaced as a
dedicated section in the rendered Markdown.

Design:
- Extract every frequency mention in the controller's transcripts (digits
  AND spelled-out forms in EN and ES, since Whisper output varies).
- Infer the service (TWR/GND/APP/DEP/DEL/ATIS) from a keyword window
  around the mention.
- Compare against the airport's expected frequency for that service.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable, Optional

# Fallback when the airport has no parsed COM frequencies in Redis. Kept
# inline so this module stays dependency-free and unit-testable in isolation.
_DEFAULT_FREQS_MHZ: dict[str, float] = {
    "ATIS": 121.980,
    "DEL":  121.805,
    "GND":  121.655,
    "TWR":  118.330,
}

# Tolerance for matching said vs expected frequency (5 kHz absorbs the
# difference between 25 kHz and 8.33 kHz channel rounding).
_FREQ_TOLERANCE_MHZ = 0.005

# Service keyword window (characters around the frequency span).
_KEYWORD_WINDOW = 60

_SERVICE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("TWR",  ("tower", "twr", "torre")),
    ("GND",  ("ground", "gnd", "tierra", "rodaje")),
    ("APP",  ("approach", "app", "aproximacion", "aproximación")),
    ("DEP",  ("departure", "dep", "salida")),
    ("DEL",  ("delivery", "clearance", "entrega", "autorizacion", "autorización")),
    ("ATIS", ("atis", "information", "informacion", "información")),
]

# Spelled digits → numeric. Includes ICAO "niner" plus EN and ES base words.
_SPELLED_DIGITS: dict[str, str] = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "niner": "9",
    "cero": "0", "uno": "1", "dos": "2", "tres": "3", "cuatro": "4",
    "cinco": "5", "seis": "6", "siete": "7", "ocho": "8", "nueve": "9",
}
_DECIMAL_TOKENS = ("decimal", "point", "punto", "coma")

# 110-129 MHz covers the VHF aviation comm band used at airports.
_FREQ_NUMERIC_RE = re.compile(r"\b(1[12]\d)[.,](\d{1,3})\b")
_DIGIT_DOT_RUN_RE = re.compile(r"(?<=\d)\s+(?=[\d.])|(?<=\.)\s+(?=\d)")


def _normalise_spelled_numbers(text: str) -> str:
    """Convert isolated spelled digits and decimal markers to digits/dot.

    "one one eight decimal three" → "1 1 8 . 3" → "118.3"
    "uno uno ocho coma tres"      → "1 1 8 . 3" → "118.3"
    """
    def _sub(match: re.Match) -> str:
        word = match.group(0).lower()
        if word in _SPELLED_DIGITS:
            return _SPELLED_DIGITS[word]
        return "."  # decimal marker

    pattern = r"\b(" + "|".join(
        list(_SPELLED_DIGITS.keys()) + list(_DECIMAL_TOKENS)
    ) + r")\b"
    replaced = re.sub(pattern, _sub, text, flags=re.IGNORECASE)
    # Collapse "1 1 8 . 3" → "118.3" without touching unrelated whitespace.
    return _DIGIT_DOT_RUN_RE.sub("", replaced)


def _find_mentions(text: str) -> list[tuple[float, int, int]]:
    """Return [(freq_mhz, span_start, span_end)] for every mention in text.

    Spans refer to the *original* text, not the normalised one, so the
    surrounding keyword window is meaningful.
    """
    mentions: list[tuple[float, int, int]] = []
    seen: set[tuple[int, int]] = set()

    for m in _FREQ_NUMERIC_RE.finditer(text):
        mhz = float(f"{m.group(1)}.{m.group(2)}")
        span = m.span()
        mentions.append((mhz, span[0], span[1]))
        seen.add(span)

    # Spelled forms: detect them on a normalised copy and map back to the
    # earliest service-keyword window we can find in the original text.
    normalised = _normalise_spelled_numbers(text)
    for m in _FREQ_NUMERIC_RE.finditer(normalised):
        mhz = float(f"{m.group(1)}.{m.group(2)}")
        # Skip if the same numeric mention was already in the original.
        if any(abs(mhz - existing) < 0.0005 for existing, _, _ in mentions):
            continue
        # Use the whole text as the keyword search range — we lost the
        # exact span when we collapsed spaces, but for service inference
        # the entire transmission is a reasonable scope.
        mentions.append((mhz, 0, len(text)))

    return mentions


def _infer_service(text: str, span_start: int, span_end: int) -> Optional[str]:
    """Pick the first service keyword found within ±_KEYWORD_WINDOW chars.

    Returns one of "ATIS", "UNICOM", "DEL", "GND", "TWR", "APP", "DEP" or None.
    """
    lo = max(0, span_start - _KEYWORD_WINDOW)
    hi = min(len(text), span_end + _KEYWORD_WINDOW)
    window = text[lo:hi].lower()
    for service, keywords in _SERVICE_KEYWORDS:
        for kw in keywords:
            if re.search(r"\b" + re.escape(kw) + r"\b", window):
                return service
    return None


def _expected_for(service: Optional[str], com_frequencies: list[dict]) -> Optional[float]:
    """Look up the expected MHz for a service.

    First the airport-specific list (from apt.dat), then the hardcoded
    defaults. Returns None if neither has the service.
    """
    if not service:
        return None
    for f in com_frequencies or []:
        if str(f.get("service", "")).upper() == service:
            try:
                return float(f["frequency_mhz"])
            except (TypeError, ValueError, KeyError):
                continue
    return _DEFAULT_FREQS_MHZ.get(service)


def _fmt_ts(ts: float | str | None) -> str:
    if ts is None:
        return "--:--:--"
    try:
        if isinstance(ts, str):
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
        return dt.strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return "--:--:--"


def audit_frequencies(
    transcripts: Iterable[dict],
    com_frequencies: Optional[list[dict]] = None,
) -> dict:
    """Walk the controller transcripts and audit every frequency mention.

    Args:
        transcripts: list of {"ts": float, "text": str} as stored in Redis.
        com_frequencies: list of {"service", "frequency_mhz", "name"} dicts
            from apt.dat parsing. Empty/None falls back to defaults.

    Returns:
        {
            "mentions": int,
            "correct": int,
            "incorrect": int,
            "unknown": int,
            "findings": [
                {"ts": float, "hhmmss": "HH:MM:SS", "quote": str,
                 "said_freq": float, "expected_freq": float | None,
                 "service": str | None, "verdict": "good"|"bad"|"unknown"}
            ],
        }
    """
    com_frequencies = com_frequencies or []
    findings: list[dict] = []
    correct = incorrect = unknown = 0

    for t in transcripts or []:
        text = (t.get("text") or "").strip()
        if not text:
            continue
        ts = t.get("ts")

        for said, span_start, span_end in _find_mentions(text):
            service = _infer_service(text, span_start, span_end)
            expected = _expected_for(service, com_frequencies)
            if expected is None:
                verdict = "unknown"
                unknown += 1
            elif abs(said - expected) <= _FREQ_TOLERANCE_MHZ:
                verdict = "good"
                correct += 1
            else:
                verdict = "bad"
                incorrect += 1

            findings.append({
                "ts": ts,
                "hhmmss": _fmt_ts(ts),
                "quote": text,
                "said_freq": said,
                "expected_freq": expected,
                "service": service,
                "verdict": verdict,
            })

    return {
        "mentions": len(findings),
        "correct": correct,
        "incorrect": incorrect,
        "unknown": unknown,
        "findings": findings,
    }


def render_audit_markdown(audit: dict) -> str:
    """Format the audit as a Markdown section for the debrief.

    Returns an empty string when there were no mentions, so the caller
    can simply concatenate the result.
    """
    findings = audit.get("findings") or []
    if not findings:
        return ""

    lines = ["## Frequency accuracy"]
    lines.append(
        f"{audit.get('mentions', 0)} mention(s) — "
        f"{audit.get('correct', 0)} correct, "
        f"{audit.get('incorrect', 0)} wrong, "
        f"{audit.get('unknown', 0)} unverifiable."
    )
    lines.append("")
    lines.append("| Time | Service | Said | Expected | Verdict | Quote |")
    lines.append("|------|---------|------|----------|---------|-------|")
    for f in findings:
        verdict = f.get("verdict", "?")
        mark = "✔" if verdict == "good" else "✘" if verdict == "bad" else "·"
        expected = f.get("expected_freq")
        expected_s = f"{expected:.3f}" if isinstance(expected, (int, float)) else "—"
        quote = (f.get("quote") or "").replace("|", "\\|").replace("\n", " ")
        if len(quote) > 80:
            quote = quote[:77] + "..."
        lines.append(
            f"| {f.get('hhmmss', '--:--:--')} "
            f"| {f.get('service') or '—'} "
            f"| {f.get('said_freq', 0):.3f} "
            f"| {expected_s} "
            f"| {mark} {verdict} "
            f"| {quote} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_audit_for_prompt(audit: dict) -> str:
    """Compact text block injected into the debrief LLM prompt.

    Empty if there were no mentions — caller simply skips the block.
    """
    findings = audit.get("findings") or []
    if not findings:
        return ""
    lines = [
        "FREQUENCY AUDIT (deterministic, ground truth from apt.dat):",
        f"- {audit.get('mentions', 0)} frequency mention(s) detected",
        f"- {audit.get('correct', 0)} correct, "
        f"{audit.get('incorrect', 0)} wrong, "
        f"{audit.get('unknown', 0)} unverifiable",
    ]
    for f in findings:
        expected = f.get("expected_freq")
        expected_s = f"{expected:.3f}" if isinstance(expected, (int, float)) else "n/a"
        lines.append(
            f"- [{f.get('hhmmss', '--:--:--')}] said {f.get('said_freq', 0):.3f} "
            f"to {f.get('service') or 'unknown service'} — "
            f"expected {expected_s} — {str(f.get('verdict', '?')).upper()}"
        )
    return "\n".join(lines)
