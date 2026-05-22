"""Extract per-stage latencies from logs/pipeline.log.

The pipeline log records every transition of the voice-to-DataRef pipeline
with ISO-8601 second-precision timestamps. This script pairs *_INPUT with
*_REPLY events (and similar pairs) inside the same session, computes deltas,
and reports n/min/median/p95/max for each stage. Used by memoria 5.4.1.

Usage:
    python scripts/analyze_pipeline_log.py
"""
from __future__ import annotations

import csv
import statistics
from datetime import datetime
from pathlib import Path

LOG_PATH = Path("logs/pipeline.log")
CSV_OUT = Path("output/latencies.csv")


# Pairs of (input_event, output_event) per stage. The dict order defines the
# order the stages appear in the output table.
STAGE_PAIRS = {
    "ASR (post-procesado LLM)": ("WHISPER_RAW", "LLM_CORRECTED"),
    "Agente DEL":                ("DEL_INPUT", "DEL_REPLY"),
    "Agente GND":                ("GND_INPUT", "GND_REPLY"),
    "Agente TWR":                ("TWR_INPUT", "TWR_REPLY"),
}


def parse_log(path: Path):
    """Yield (timestamp, session_id, agent, event) tuples from pipeline.log."""
    for raw in path.read_text(encoding="utf-8").splitlines():
        parts = [p.strip() for p in raw.split("|", 4)]
        if len(parts) < 4:
            continue
        ts_str, session_field, _agent, event_field = parts[:4]
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        session_id = session_field.removeprefix("session=").strip()
        event = event_field.strip()
        yield ts, session_id, event


def collect_pairs(events, input_name: str, output_name: str):
    """For each session, pair successive INPUT/REPLY events in order."""
    by_session: dict[str, list[tuple[datetime, str]]] = {}
    for ts, sid, ev in events:
        if ev not in (input_name, output_name):
            continue
        by_session.setdefault(sid, []).append((ts, ev))

    deltas: list[float] = []
    for sid, items in by_session.items():
        items.sort(key=lambda x: x[0])
        pending_input: datetime | None = None
        for ts, ev in items:
            if ev == input_name:
                pending_input = ts
            elif ev == output_name and pending_input is not None:
                deltas.append((ts - pending_input).total_seconds())
                pending_input = None
    return deltas


def collect_orch_handoff(events):
    """Time between *_REPLY of any agent and the next ORCH_ROUTE in the same session."""
    by_session: dict[str, list[tuple[datetime, str]]] = {}
    for ts, sid, ev in events:
        if ev.endswith("_REPLY") or ev == "ORCH_ROUTE":
            by_session.setdefault(sid, []).append((ts, ev))

    deltas: list[float] = []
    for items in by_session.values():
        items.sort(key=lambda x: x[0])
        pending_reply: datetime | None = None
        for ts, ev in items:
            if ev.endswith("_REPLY"):
                pending_reply = ts
            elif ev == "ORCH_ROUTE" and pending_reply is not None:
                deltas.append((ts - pending_reply).total_seconds())
                pending_reply = None
    return deltas


def percentile(values, p):
    if not values:
        return float("nan")
    return statistics.quantiles(values, n=100, method="inclusive")[p - 1]


def summarise(deltas):
    if not deltas:
        return None
    return {
        "n": len(deltas),
        "min": min(deltas),
        "p50": statistics.median(deltas),
        "p95": percentile(deltas, 95) if len(deltas) >= 2 else max(deltas),
        "max": max(deltas),
    }


def main():
    events = list(parse_log(LOG_PATH))
    print(f"Loaded {len(events)} events from {LOG_PATH}")

    rows = []
    for label, (ipt, opt) in STAGE_PAIRS.items():
        deltas = collect_pairs(events, ipt, opt)
        rows.append((label, summarise(deltas)))

    # Orchestrator hand-off as a separate stage
    rows.append(("Orquestador (post-reply)", summarise(collect_orch_handoff(events))))

    # Print pretty table
    print()
    print(f"{'Etapa':<28} {'n':>4} {'min(s)':>8} {'p50(s)':>8} {'p95(s)':>8} {'max(s)':>8}")
    print("-" * 70)
    for label, s in rows:
        if s is None:
            print(f"{label:<28} {'--':>4} {'--':>8} {'--':>8} {'--':>8} {'--':>8}")
        else:
            print(f"{label:<28} {s['n']:>4} {s['min']:>8.1f} "
                  f"{s['p50']:>8.1f} {s['p95']:>8.1f} {s['max']:>8.1f}")

    # CSV out
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stage", "n", "min_s", "p50_s", "p95_s", "max_s"])
        for label, s in rows:
            if s is None:
                w.writerow([label, 0, "", "", "", ""])
            else:
                w.writerow([label, s["n"],
                            round(s["min"], 1), round(s["p50"], 1),
                            round(s["p95"], 1), round(s["max"], 1)])
    print(f"\nWrote: {CSV_OUT}")


if __name__ == "__main__":
    main()
