"""Build the chronological timeline text that feeds the debrief LLM.

Pure functions, no I/O; unit-testable standalone. Inputs are the raw
lists the `session_log` returns plus the clearance rows from Postgres.
"""

from datetime import datetime, timezone
from typing import Iterable, Optional


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


def _coerce_ts(ts) -> float:
    if ts is None:
        return 0.0
    if isinstance(ts, (int, float)):
        return float(ts)
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return 0.0


def build_timeline(
    transcripts: Iterable[dict],
    agent_replies: Iterable[dict],
    events: Iterable[dict],
    clearances: Iterable[dict],
) -> str:
    """Interleave everything by timestamp into a deterministic text block.

    Lines:
      [HH:MM:SS] CTRL: "<text>"
      [HH:MM:SS] PILOT (DEP, REG/CALLSIGN): "<reply>"
      [HH:MM:SS] EVENT (REG): <event> <extra>
      [HH:MM:SS] CLEARANCE (REG, DEP): <short summary>
    """
    items: list[tuple[float, str]] = []

    for t in transcripts or []:
        text = (t.get("text") or "").strip()
        if not text:
            continue
        ts = _coerce_ts(t.get("ts"))
        items.append((ts, f'[{_fmt_ts(ts)}] CTRL: "{text}"'))

    for r in agent_replies or []:
        reply = (r.get("reply") or "").strip()
        if not reply:
            continue
        ts = _coerce_ts(r.get("ts"))
        reg = r.get("registration") or "-"
        cs = r.get("callsign") or reg
        dep = r.get("dep") or "-"
        items.append((ts, f'[{_fmt_ts(ts)}] PILOT ({dep}, {reg}/{cs}): "{reply}"'))

    for e in events or []:
        ts = _coerce_ts(e.get("ts"))
        reg = e.get("registration") or "-"
        ev = e.get("event") or "event"
        extra = e.get("extra") or {}
        tail = ""
        if isinstance(extra, dict):
            # Keep it short; skip verbose structures
            parts = []
            for k, v in extra.items():
                if v is None or v == "":
                    continue
                if isinstance(v, (str, int, float, bool)):
                    parts.append(f"{k}={v}")
            if parts:
                tail = " " + " ".join(parts)
        items.append((ts, f"[{_fmt_ts(ts)}] EVENT ({reg}): {ev}{tail}"))

    for c in clearances or []:
        ts = _coerce_ts(c.get("updated_at") or c.get("cleared_at"))
        reg = c.get("aircraft_registration") or "-"
        dep = c.get("dependency") or "-"
        summary_parts = []
        for field in ("squawk", "initial_altitude", "instrumental_departure",
                       "runway_in_use", "destination_icao"):
            val = c.get(field)
            if val not in (None, "", 0):
                summary_parts.append(f"{field}={val}")
        tail = (" " + " ".join(summary_parts)) if summary_parts else ""
        items.append((ts, f"[{_fmt_ts(ts)}] CLEARANCE ({reg}, {dep}):{tail}"))

    items.sort(key=lambda kv: kv[0])
    return "\n".join(line for _, line in items)


def truncate_timeline(text: str, max_chars: int = 24000) -> str:
    """Keep the tail of the timeline when it's too long; prepend an
    elision marker listing how many lines were dropped."""
    if len(text) <= max_chars:
        return text
    lines = text.splitlines()
    kept: list[str] = []
    total = 0
    for line in reversed(lines):
        total += len(line) + 1
        if total > max_chars:
            break
        kept.append(line)
    kept.reverse()
    dropped = len(lines) - len(kept)
    if dropped > 0:
        prefix = f"[... {dropped} earlier entries omitted ...]"
        return prefix + "\n" + "\n".join(kept)
    return "\n".join(kept)


def summarise_stats(
    transcripts: Iterable[dict],
    agent_replies: Iterable[dict],
    events: Iterable[dict],
    clearances: Iterable[dict],
) -> dict:
    """Cheap counts the prompt can quote without analysing the text."""
    transcripts = list(transcripts or [])
    replies = list(agent_replies or [])
    events = list(events or [])
    clearances = list(clearances or [])
    dep_counts = {"DEL": 0, "GND": 0, "TWR": 0}
    for r in replies:
        d = (r.get("dep") or "").upper()
        if d in dep_counts:
            dep_counts[d] += 1
    aircraft_set: set[str] = set()
    for c in clearances:
        reg = c.get("aircraft_registration")
        if reg:
            aircraft_set.add(reg)
    for r in replies:
        reg = r.get("registration")
        if reg:
            aircraft_set.add(reg)
    ts_values = [
        _coerce_ts(t.get("ts")) for t in transcripts
        if _coerce_ts(t.get("ts")) > 0
    ]
    duration_s: Optional[float] = None
    if len(ts_values) >= 2:
        duration_s = max(ts_values) - min(ts_values)
    return {
        "transcript_count": len(transcripts),
        "agent_reply_count": len(replies),
        "event_count": len(events),
        "clearance_count": len(clearances),
        "aircraft_count": len(aircraft_set),
        "dep_reply_counts": dep_counts,
        "duration_seconds": duration_s,
    }
