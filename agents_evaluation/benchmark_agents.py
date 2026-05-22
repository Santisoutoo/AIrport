"""Benchmark the three ATC agents (DEL, GND, TWR) against the pilot-readback corpus.

For each entry of the 142-line corpus (42 DEL + 50 GND + 50 TWR), the script:
  1. Sends the ATC message to the corresponding Cloud Run endpoint.
  2. Records latency, HTTP status, presence of a clearance_data block,
     and whether the clearance is "complete" (all required numeric fields
     filled in for entries that should carry a structured clearance).
  3. Dumps per-entry rows to `output/agent_benchmark.csv` and prints an
     aggregated summary per dependency (n, % schema-valid, % clearance-
     complete, p50/p95 latency).

Reads the endpoints from .env (DEL_AGENT_URL, GND_AGENT_URL, TWR_AGENT_URL).

Used by memoria 5.2.2.
"""
from __future__ import annotations

import csv
import json
import os
import re
import statistics
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

CORPUS_DIR = Path("agents_evaluation/corpus_wer")
CSV_OUT = Path("output/agent_benchmark.csv")

REQUEST_TIMEOUT_S = 60

# Endpoint suffix per dependency (full URL = base_url + suffix)
SUFFIX = {
    "DEL": "/agents/delivery/run",
    "GND": "/agents/ground/run",
    "TWR": "/agents/tower/run",
}

# Each agent emits a different structured block in the response:
#   DEL -> "clearance_data"
#   GND -> "taxi_data"
#   TWR -> "reply_data"
# REQUIRED_FIELDS lists fields that must be populated for the block to be
# considered a "complete" structured response. If the block itself is null
# the response is treated as an acknowledgement and counted as complete.
STRUCTURED_KEY = {
    "DEL": "clearance_data",
    "GND": "taxi_data",
    "TWR": "reply_data",
}
REQUIRED_FIELDS = {
    "DEL": ["squawk", "initial_altitude", "instrumental_departure", "runway_in_use"],
    "GND": ["taxi_route", "runway_in_use"],
    "TWR": ["runway_in_use"],
}


def load_env_urls() -> dict[str, str]:
    """Read DEL/GND/TWR base URLs from .env (or os.environ if missing)."""
    env = {}
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*([A-Z_]+)\s*=\s*(.+?)\s*$", line)
            if m:
                env[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    urls = {}
    for dep in ("DEL", "GND", "TWR"):
        key = f"{dep}_AGENT_URL"
        urls[dep] = env.get(key) or os.environ.get(key, "")
    return urls


def parse_corpus(path: Path) -> list[tuple[str, str, str]]:
    """Return list of (entry_id, atc_text, pilot_text) parsed from a corpus_wer_*.txt file."""
    entries: list[tuple[str, str, str]] = []
    current_id = None
    atc, pilot = None, None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("#") or not line:
            continue
        m = re.match(r"^\[([a-z]+_\d+)\]$", line)
        if m:
            if current_id and atc is not None:
                entries.append((current_id, atc, pilot or ""))
            current_id = m.group(1)
            atc, pilot = None, None
        elif line.startswith(">"):
            atc = line[1:].strip()
        elif line.startswith("<"):
            pilot = line[1:].strip()
    if current_id and atc is not None:
        entries.append((current_id, atc, pilot or ""))
    return entries


def call_agent(url: str, session_id: str, message: str) -> tuple[int, float, dict | None, str]:
    """POST to the agent and return (status, latency_s, response_dict, error_msg)."""
    payload = json.dumps({"session_id": session_id, "message": message}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
            elapsed = time.perf_counter() - t0
            body = resp.read().decode("utf-8")
            return resp.status, elapsed, json.loads(body), ""
    except urllib.error.HTTPError as e:
        return e.code, time.perf_counter() - t0, None, f"HTTPError: {e}"
    except Exception as e:
        return -1, time.perf_counter() - t0, None, f"{type(e).__name__}: {e}"


def is_clearance_complete(dep: str, block: dict | None) -> bool:
    """True if structured block is None (acknowledgement) OR all required fields filled."""
    if block is None:
        return True
    for f in REQUIRED_FIELDS[dep]:
        v = block.get(f)
        if v is None or v == "":
            return False
    return True


def summarise(rows: list[dict], dep: str) -> dict:
    sub = [r for r in rows if r["dep"] == dep]
    n = len(sub)
    if n == 0:
        return {"dep": dep, "n": 0, "pct_schema_valid": 0.0,
                "pct_clearance_complete": 0.0, "p50_s": 0.0, "p95_s": 0.0}
    schema_ok = sum(1 for r in sub if r["schema_valid"])
    clearance_ok = sum(1 for r in sub if r["clearance_complete"])
    lats = [r["latency_s"] for r in sub if r["schema_valid"]]
    p50 = statistics.median(lats) if lats else 0.0
    p95 = (
        statistics.quantiles(lats, n=100, method="inclusive")[94]
        if len(lats) >= 2 else (lats[0] if lats else 0.0)
    )
    return {
        "dep": dep,
        "n": n,
        "pct_schema_valid": 100.0 * schema_ok / n,
        "pct_clearance_complete": 100.0 * clearance_ok / n,
        "p50_s": p50,
        "p95_s": p95,
    }


def main():
    urls = load_env_urls()
    print("Endpoints:")
    for dep, url in urls.items():
        print(f"  {dep}: {url or '[NOT SET]'}")

    rows: list[dict] = []
    session_id = f"bench-{uuid.uuid4().hex[:8]}"

    for dep in ("DEL", "GND", "TWR"):
        base = urls[dep]
        if not base:
            print(f"\n[{dep}] skipping — no endpoint configured")
            continue
        full_url = base.rstrip("/") + SUFFIX[dep]
        corpus_path = CORPUS_DIR / dep.lower() / f"corpus_wer_{dep.lower()}.txt"
        entries = parse_corpus(corpus_path)
        print(f"\n[{dep}] {len(entries)} corpus entries → {full_url}")

        struct_key = STRUCTURED_KEY[dep]
        for i, (entry_id, atc_text, _pilot) in enumerate(entries, 1):
            status, lat, resp, err = call_agent(full_url, session_id, atc_text)
            schema_valid = (status == 200) and (resp is not None)
            block = resp.get(struct_key) if isinstance(resp, dict) else None
            clearance_complete = is_clearance_complete(dep, block) if schema_valid else False
            reply_text = (resp or {}).get("reply", "") if schema_valid else ""
            rows.append({
                "dep": dep,
                "entry_id": entry_id,
                "status": status,
                "latency_s": round(lat, 3),
                "schema_valid": schema_valid,
                "clearance_present": block is not None,
                "clearance_complete": clearance_complete,
                "reply_chars": len(reply_text),
                "error": err,
            })
            mark = "OK" if schema_valid else "FAIL"
            print(f"  [{i:3d}/{len(entries)}] {entry_id}: {mark} "
                  f"({lat:.1f}s, status={status})", flush=True)

    # Write CSV
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "dep", "entry_id", "status", "latency_s",
            "schema_valid", "clearance_present", "clearance_complete",
            "reply_chars", "error",
        ])
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote: {CSV_OUT}")

    # Aggregated summary
    print()
    print(f"{'Dep':<5} {'n':>4} {'%schema':>9} {'%complete':>11} {'p50(s)':>8} {'p95(s)':>8}")
    print("-" * 55)
    for dep in ("DEL", "GND", "TWR"):
        s = summarise(rows, dep)
        print(f"{s['dep']:<5} {s['n']:>4} {s['pct_schema_valid']:>8.1f}% "
              f"{s['pct_clearance_complete']:>10.1f}% "
              f"{s['p50_s']:>8.1f} {s['p95_s']:>8.1f}")


if __name__ == "__main__":
    main()
