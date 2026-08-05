"""LLM-as-judge evaluation of the three ATC agents' reply generation.

For every corpus entry (100 DEL + 100 GND + 100 TWR = 300), this script:
  1. Sends the controller transmission (the ``>`` line) to the matching Cloud Run
     agent with a *fresh* session_id, timing the reply generation.
  2. Asks an LLM judge (``gemini-2.5-pro`` on Vertex) to score the agent's spoken
     readback against the transmission and the reference readback (the ``<`` line),
     timing the judge call too.
  3. Writes everything to CSV under ``agents_evaluation/output/`` and prints three
     summary tables (per-dependency pass rate + generation latency, per-dimension
     breakdown, and a catalogue of the concrete failures).

Three workers run in parallel (one per dependency, serial within each), following
the convention of ``validate_agents.py``. The judge uses JSON mode with a strict
``response_schema`` (temperature 0) so verdicts are stable and machine-readable.

Reads endpoints from .env (DEL/GND/TWR_AGENT_URL) and loads the rest of .env into
the process environment so ``genai.Client()`` picks up GOOGLE_GENAI_USE_VERTEXAI /
GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION / GOOGLE_APPLICATION_CREDENTIALS.

Feeds memoria section 5.2.2.

Usage:
  python agents_evaluation/judge_responses.py --selftest          # 2 judge calls, no agents
  python agents_evaluation/judge_responses.py --limit 2 --deps del
  python agents_evaluation/judge_responses.py                     # full 300-entry run
  python agents_evaluation/judge_responses.py --rejudge agents_evaluation/output/agent_judge_full.csv

CLI:
  --limit N            only the first N entries per dependency
  --deps del,gnd,twr   subset of dependencies (default all three)
  --judge-model ID     judge model (default gemini-2.5-pro, or env JUDGE_MODEL)
  --timeout SECONDS    per-agent-request timeout (default 180, or env JUDGE_AGENT_TIMEOUT_S)
  --rejudge CSV        re-run only the judge phase from a previous full CSV (no agent calls)
  --selftest           2 hardcoded judge calls (expected PASS + expected FAIL); no agent calls
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from benchmark_agents import STRUCTURED_KEY, SUFFIX, load_env_urls, parse_corpus
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from validate_agents import call_agent_with_retry

CORPUS_DIR = Path("agents_evaluation/corpus_wer")
OUT_DIR = Path("agents_evaluation/output")
FULL_CSV = OUT_DIR / "agent_judge_full.csv"
REVIEW_CSV = OUT_DIR / "agent_judge_review.csv"
TABLE_SUMMARY_CSV = OUT_DIR / "agent_judge_table_summary.csv"
TABLE_DIMENSIONS_CSV = OUT_DIR / "agent_judge_table_dimensions.csv"
TABLE_FAILURES_CSV = OUT_DIR / "agent_judge_table_failures.csv"

ORDER = ["DEL", "GND", "TWR"]

DEFAULT_JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "gemini-2.5-pro")
DEFAULT_TIMEOUT_S = int(os.environ.get("JUDGE_AGENT_TIMEOUT_S", "180"))
MAX_JUDGE_ATTEMPTS = 4

# HTTP statuses worth retrying on the judge call (Vertex throttling / churn).
_RETRY_CODES = {429, 500, 502, 503, 504}

# Short context handed to the judge so "required readback items" is unambiguous.
DEP_CONTEXT = {
    "DEL": (
        "Clearance Delivery. The controller issues an IFR departure clearance "
        "(destination/SID, initial climb, squawk, QNH, runway) or a "
        "frequency-change instruction the pilot must acknowledge."
    ),
    "GND": (
        "Ground. The controller issues pushback and taxi instructions (taxi "
        "route, holding point, runway) or a pushback approval the pilot "
        "acknowledges."
    ),
    "TWR": (
        "Tower. The controller issues line-up / take-off / landing clearances "
        "(runway, wind, clearance type) or an instruction the pilot "
        "acknowledges."
    ),
}

FULL_FIELDS = [
    "dep",
    "entry_id",
    "session_id",
    "atc_text",
    "expected_readback",
    "agent_reply",
    "structured_data",
    "status",
    "agent_latency_s",
    "judge_latency_s",
    "values_correct",
    "completeness",
    "no_hallucination",
    "phraseology_score",
    "overall",
    "justification",
    "error",
]

REVIEW_FIELDS = [
    "dep",
    "entry_id",
    "atc_text",
    "expected_readback",
    "agent_reply",
    "judge_values_correct",
    "judge_completeness",
    "judge_no_hallucination",
    "judge_phraseology_score",
    "judge_overall",
    "judge_justification",
    "human_verdict",
    "human_notes",
]


# --------------------------------------------------------------------------- #
# .env -> os.environ (so genai.Client() sees the Vertex config)
# --------------------------------------------------------------------------- #
def load_dotenv_into_environ(path: Path = Path(".env")) -> None:
    """Populate os.environ from .env without overriding existing variables."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


# --------------------------------------------------------------------------- #
# The judge: JSON mode + strict schema (mirrors debrief_agent.py)
# --------------------------------------------------------------------------- #
_JUDGE_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "values_correct": {"type": "STRING", "enum": ["PASS", "FAIL", "N/A"]},
        "completeness": {"type": "STRING", "enum": ["PASS", "FAIL", "N/A"]},
        "no_hallucination": {"type": "STRING", "enum": ["PASS", "FAIL"]},
        "phraseology_score": {"type": "INTEGER"},  # 1-5
        "overall": {"type": "STRING", "enum": ["PASS", "FAIL"]},
        "justification": {"type": "STRING"},  # one line, Spanish
    },
    "required": ["values_correct", "completeness", "no_hallucination", "phraseology_score", "overall", "justification"],
}

JUDGE_SYSTEM_PROMPT = """You are an expert ICAO radiotelephony examiner. You are grading an AI ATC-agent that plays the PILOT role. Judge ONLY the agent's spoken readback ("agent_reply") against the controller transmission ("atc_transmission"). "expected_readback" is ONE valid reference readback: it is an example, not the only correct wording. Do NOT penalise a different phrasing that is still correct.

Return these six fields:

- values_correct: "PASS" if EVERY operational value present in the readback (squawk, runway, SID / departure, initial altitude, QNH / altimeter, frequency, taxi route, holding point) matches the value in the controller transmission; "FAIL" if any value is wrong; "N/A" if the transmission carries no operational values (e.g. a bare pushback or line-up acknowledgement).
- completeness: "PASS" if the readback contains every item that ICAO requires to be read back for this instruction; "FAIL" if a mandatory item is missing; "N/A" for pure acknowledgements that carry no mandatory readback.
- no_hallucination: "PASS" if the readback invents no value or instruction that is absent from the transmission; "FAIL" if it adds fabricated content.
- phraseology_score: integer 1-5 rating ICAO pilot phraseology. Consider phonetic delivery of digits, callsign placed at the END of the readback, absence of controller-style wording, and use of standard terms. 5 = textbook pilot readback; 3 = understandable but sloppy; 1 = wrong role or unintelligible.
- overall: "FAIL" if ANY of values_correct / completeness / no_hallucination is "FAIL", OR if phraseology_score <= 2; otherwise "PASS".
- justification: ONE concise sentence in Spanish naming the concrete discrepancy (or confirming that the readback is correct).

Grade strictly but fairly. Output only the JSON object."""

_client: genai.Client | None = None


def _get_judge_client() -> genai.Client:
    """Lazy Vertex client; reads GOOGLE_GENAI_USE_VERTEXAI / GOOGLE_CLOUD_* /
    GOOGLE_APPLICATION_CREDENTIALS from the environment (see .env)."""
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


def _build_judge_prompt(dep: str, atc_text: str, expected_readback: str, agent_reply: str, structured_json: str) -> str:
    return (
        f"DEPENDENCY: {dep}. {DEP_CONTEXT.get(dep, '')}\n\n"
        f"atc_transmission:\n{atc_text}\n\n"
        f"expected_readback (ONE valid reference, not the only correct wording):\n"
        f"{expected_readback}\n\n"
        f"agent_reply (THIS is what you grade):\n{agent_reply}\n\n"
        f"structured_data (fields the agent parsed, for context only):\n"
        f"{structured_json}\n"
    )


def judge_reply(
    dep: str, atc_text: str, expected_readback: str, agent_reply: str, structured_json: str, judge_model: str
) -> tuple[dict, float, str]:
    """Return (verdict_dict, judge_latency_s, error). error == '' on success."""
    client = _get_judge_client()
    config = types.GenerateContentConfig(
        system_instruction=JUDGE_SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=_JUDGE_SCHEMA,
        temperature=0.0,
    )
    prompt = _build_judge_prompt(dep, atc_text, expected_readback, agent_reply, structured_json)

    last_exc: Exception | None = None
    for attempt in range(MAX_JUDGE_ATTEMPTS):
        retryable = False
        try:
            t0 = time.perf_counter()
            resp = client.models.generate_content(model=judge_model, contents=prompt, config=config)
            elapsed = round(time.perf_counter() - t0, 3)
            verdict = json.loads(resp.text or "{}")
            return verdict, elapsed, ""
        except genai_errors.APIError as exc:
            last_exc = exc
            retryable = getattr(exc, "code", None) in _RETRY_CODES
        except json.JSONDecodeError as exc:
            last_exc = exc
            retryable = False
        except Exception as exc:  # noqa: BLE001 - transient network blips
            last_exc = exc
            retryable = True
        if not retryable or attempt == MAX_JUDGE_ATTEMPTS - 1:
            break
        # exponential backoff with jitter: 2s, 4s, 8s, 16s ... capped at 30s
        time.sleep(min(2 ** (attempt + 1) + random.random(), 30))

    return {}, 0.0, f"judge_error: {type(last_exc).__name__}: {str(last_exc)[:200]}"


# --------------------------------------------------------------------------- #
# Per-entry row assembly
# --------------------------------------------------------------------------- #
def build_full_row(
    dep: str,
    entry_id: str,
    session_id: str,
    atc_text: str,
    expected_readback: str,
    agent_reply: str,
    structured_json: str,
    status: int,
    agent_latency_s,
    agent_error: str,
    judge_model: str,
) -> dict:
    row = {
        "dep": dep,
        "entry_id": entry_id,
        "session_id": session_id,
        "atc_text": atc_text,
        "expected_readback": expected_readback,
        "agent_reply": agent_reply,
        "structured_data": structured_json,
        "status": status,
        "agent_latency_s": agent_latency_s,
        "judge_latency_s": "",
        "values_correct": "",
        "completeness": "",
        "no_hallucination": "",
        "phraseology_score": "",
        "overall": "",
        "justification": "",
        "error": agent_error or "",
    }
    if agent_error or status != 200 or not agent_reply:
        if not row["error"]:
            row["error"] = f"agent_no_reply (status={status})"
        return row

    verdict, jlat, jerr = judge_reply(dep, atc_text, expected_readback, agent_reply, structured_json, judge_model)
    row["judge_latency_s"] = jlat
    if jerr:
        row["error"] = jerr
        return row
    row["values_correct"] = verdict.get("values_correct", "")
    row["completeness"] = verdict.get("completeness", "")
    row["no_hallucination"] = verdict.get("no_hallucination", "")
    row["phraseology_score"] = verdict.get("phraseology_score", "")
    row["overall"] = verdict.get("overall", "")
    row["justification"] = verdict.get("justification", "")
    return row


def run_dependency(dep: str, base_url: str, entries: list, judge_model: str, timeout_s: int) -> list[dict]:
    if not base_url:
        print(f"[{dep}] skip - no endpoint configured", flush=True)
        return []
    full_url = base_url.rstrip("/") + SUFFIX[dep]
    struct_key = STRUCTURED_KEY[dep]
    print(f"[{dep}] {len(entries)} entries -> {full_url}", flush=True)

    rows: list[dict] = []
    for i, (entry_id, atc_text, pilot_text) in enumerate(entries, 1):
        session_id = f"judge-{dep.lower()}-{entry_id}-{uuid.uuid4().hex[:6]}"
        status, lat, resp, err = call_agent_with_retry(full_url, session_id, atc_text, timeout_s)
        agent_reply = (resp or {}).get("reply", "") if isinstance(resp, dict) else ""
        block = resp.get(struct_key) if isinstance(resp, dict) else None
        structured_json = json.dumps(block, ensure_ascii=False)
        row = build_full_row(
            dep,
            entry_id,
            session_id,
            atc_text,
            pilot_text,
            agent_reply,
            structured_json,
            status,
            round(lat, 3),
            err,
            judge_model,
        )
        rows.append(row)
        mark = row["overall"] or ("ERR" if row["error"] else "?")
        print(
            f"[{dep}] [{i:3d}/{len(entries)}] {entry_id} agent={status} "
            f"judge={mark:4} (a={row['agent_latency_s']}s j={row['judge_latency_s']}s)",
            flush=True,
        )
    return rows


def run_full(deps: list[str], limit: int, judge_model: str, timeout_s: int) -> list[dict]:
    urls = load_env_urls()
    print("Endpoints:")
    for dep in deps:
        print(f"  {dep}: {urls.get(dep) or '[NOT SET]'}")
    print(f"Judge model: {judge_model}   agent timeout: {timeout_s}s")

    corpus: dict[str, list] = {}
    for dep in deps:
        path = CORPUS_DIR / dep.lower() / f"corpus_wer_{dep.lower()}.txt"
        entries = parse_corpus(path)
        if limit:
            entries = entries[:limit]
        corpus[dep] = entries

    all_rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {
            ex.submit(run_dependency, dep, urls.get(dep, ""), corpus[dep], judge_model, timeout_s): dep for dep in deps
        }
        for fut in as_completed(futs):
            dep = futs[fut]
            try:
                rows = fut.result()
            except Exception as exc:  # noqa: BLE001
                print(f"[{dep}] worker crashed: {type(exc).__name__}: {exc}", flush=True)
                rows = []
            all_rows.extend(rows)
            print(f"[{dep}] worker done ({len(rows)} rows).", flush=True)
    return all_rows


# --------------------------------------------------------------------------- #
# --rejudge: re-run only the judge phase from a previous full CSV
# --------------------------------------------------------------------------- #
def _read_full_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def rejudge_dependency(dep: str, in_rows: list[dict], judge_model: str) -> list[dict]:
    print(f"[{dep}] re-judging {len(in_rows)} rows", flush=True)
    out: list[dict] = []
    for i, r in enumerate(in_rows, 1):
        raw_status = str(r.get("status", "")).strip()
        status = int(raw_status) if raw_status.lstrip("-").isdigit() else -1
        agent_reply = r.get("agent_reply", "") or ""
        # A row with no agent reply was an agent failure; keep it as an error.
        agent_error = "" if agent_reply else (r.get("error") or f"agent_no_reply (status={status})")
        row = build_full_row(
            dep,
            r.get("entry_id", ""),
            r.get("session_id", ""),
            r.get("atc_text", ""),
            r.get("expected_readback", ""),
            agent_reply,
            r.get("structured_data", "null"),
            status,
            r.get("agent_latency_s", ""),
            agent_error,
            judge_model,
        )
        out.append(row)
        mark = row["overall"] or ("ERR" if row["error"] else "?")
        print(
            f"[{dep}] [{i:3d}/{len(in_rows)}] {row['entry_id']} judge={mark} (j={row['judge_latency_s']}s)", flush=True
        )
    return out


def run_rejudge(csv_path: Path, deps: list[str], limit: int, judge_model: str) -> list[dict]:
    print(f"Re-judging from {csv_path} (judge model: {judge_model})")
    rows_in = _read_full_csv(csv_path)
    by_dep: dict[str, list[dict]] = {d: [] for d in deps}
    for r in rows_in:
        dep = (r.get("dep") or "").upper()
        if dep in by_dep:
            by_dep[dep].append(r)
    if limit:
        for dep in by_dep:
            by_dep[dep] = by_dep[dep][:limit]

    all_rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(rejudge_dependency, dep, by_dep[dep], judge_model): dep for dep in deps if by_dep[dep]}
        for fut in as_completed(futs):
            dep = futs[fut]
            try:
                all_rows.extend(fut.result())
            except Exception as exc:  # noqa: BLE001
                print(f"[{dep}] rejudge worker crashed: {exc}", flush=True)
    return all_rows


# --------------------------------------------------------------------------- #
# Outputs
# --------------------------------------------------------------------------- #
def _order_key(row: dict):
    return (ORDER.index(row["dep"]) if row["dep"] in ORDER else 99, row["entry_id"])


def write_full(rows: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=_order_key)
    with FULL_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FULL_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(ordered)
    print(f"Wrote: {FULL_CSV}")


def _review_category(row: dict) -> int:
    """0 = judge FAIL (review first), 1 = error, 2 = PASS/other."""
    if row["overall"] == "FAIL":
        return 0
    if row["error"]:
        return 1
    return 2


def write_review(rows: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=lambda r: (_review_category(r), *_order_key(r)))
    with REVIEW_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REVIEW_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in ordered:
            w.writerow(
                {
                    "dep": r["dep"],
                    "entry_id": r["entry_id"],
                    "atc_text": r["atc_text"],
                    "expected_readback": r["expected_readback"],
                    "agent_reply": r["agent_reply"],
                    "judge_values_correct": r["values_correct"],
                    "judge_completeness": r["completeness"],
                    "judge_no_hallucination": r["no_hallucination"],
                    "judge_phraseology_score": r["phraseology_score"],
                    "judge_overall": r["overall"] or ("ERROR" if r["error"] else ""),
                    "judge_justification": r["justification"] or r["error"],
                    "human_verdict": "",
                    "human_notes": "",
                }
            )
    print(f"Wrote: {REVIEW_CSV}")


# ---- summary maths ---------------------------------------------------------- #
def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _latency_stats(vals: list[float]) -> tuple[float, float, float]:
    if not vals:
        return 0.0, 0.0, 0.0
    mean = statistics.mean(vals)
    p50 = statistics.median(vals)
    if len(vals) >= 2:
        p95 = statistics.quantiles(vals, n=100, method="inclusive")[94]
    else:
        p95 = vals[0]
    return mean, p50, p95


def _judged(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["overall"] in ("PASS", "FAIL")]


def _pass_pct(rows: list[dict], field: str) -> tuple[float, int]:
    """% PASS over rows where <field> is PASS or FAIL (N/A excluded). Returns
    (pct, n_applicable)."""
    applicable = [r for r in rows if r[field] in ("PASS", "FAIL")]
    if not applicable:
        return 0.0, 0
    n_pass = sum(1 for r in applicable if r[field] == "PASS")
    return 100.0 * n_pass / len(applicable), len(applicable)


def summary_table(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    scopes = [d for d in ORDER if any(r["dep"] == d for r in rows)] + ["TOTAL"]
    for scope in scopes:
        sub = rows if scope == "TOTAL" else [r for r in rows if r["dep"] == scope]
        if not sub:
            continue
        n = len(sub)
        n_pass = sum(1 for r in sub if r["overall"] == "PASS")
        lats = [_to_float(r["agent_latency_s"]) for r in sub if r["status"] in (200, "200")]
        lats = [x for x in lats if x is not None and x > 0]
        mean, p50, p95 = _latency_stats(lats)
        out.append(
            {
                "dep": scope,
                "n": n,
                "n_pass": n_pass,
                "pass_rate_pct": round(100.0 * n_pass / n, 1) if n else 0.0,
                "latency_mean_s": round(mean, 2),
                "latency_p50_s": round(p50, 2),
                "latency_p95_s": round(p95, 2),
            }
        )
    return out


def dimensions_table(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    scopes = [d for d in ORDER if any(r["dep"] == d for r in rows)] + ["TOTAL"]
    for scope in scopes:
        sub = _judged(rows if scope == "TOTAL" else [r for r in rows if r["dep"] == scope])
        if not sub:
            continue
        vc_pct, _ = _pass_pct(sub, "values_correct")
        cp_pct, _ = _pass_pct(sub, "completeness")
        nh_pct, _ = _pass_pct(sub, "no_hallucination")
        scores = [int(r["phraseology_score"]) for r in sub if str(r["phraseology_score"]).lstrip("-").isdigit()]
        phr_mean = statistics.mean(scores) if scores else 0.0
        phr_p5 = 100.0 * sum(1 for s in scores if s >= 4) / len(scores) if scores else 0.0
        out.append(
            {
                "dep": scope,
                "values_correct_pass_pct": round(vc_pct, 1),
                "completeness_pass_pct": round(cp_pct, 1),
                "no_hallucination_pass_pct": round(nh_pct, 1),
                "phraseology_mean": round(phr_mean, 2),
                "phraseology_p5_pct": round(phr_p5, 1),
            }
        )
    return out


def _failed_dimensions(row: dict) -> str:
    failed = []
    if row["values_correct"] == "FAIL":
        failed.append("values_correct")
    if row["completeness"] == "FAIL":
        failed.append("completeness")
    if row["no_hallucination"] == "FAIL":
        failed.append("no_hallucination")
    score = row["phraseology_score"]
    if str(score).lstrip("-").isdigit() and int(score) <= 2:
        failed.append(f"phraseology({score})")
    return ";".join(failed)


def failures_table(rows: list[dict]) -> list[dict]:
    out = []
    for r in sorted((r for r in rows if r["overall"] == "FAIL"), key=_order_key):
        out.append(
            {
                "dep": r["dep"],
                "entry_id": r["entry_id"],
                "failed_dimensions": _failed_dimensions(r),
                "phraseology_score": r["phraseology_score"],
                "justification": r["justification"],
            }
        )
    return out


def _write_table(path: Path, rows: list[dict], fields: list[str]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote: {path}")


def write_tables(rows: list[dict]) -> tuple[list, list, list]:
    summary = summary_table(rows)
    dims = dimensions_table(rows)
    fails = failures_table(rows)
    _write_table(
        TABLE_SUMMARY_CSV,
        summary,
        ["dep", "n", "n_pass", "pass_rate_pct", "latency_mean_s", "latency_p50_s", "latency_p95_s"],
    )
    _write_table(
        TABLE_DIMENSIONS_CSV,
        dims,
        [
            "dep",
            "values_correct_pass_pct",
            "completeness_pass_pct",
            "no_hallucination_pass_pct",
            "phraseology_mean",
            "phraseology_p5_pct",
        ],
    )
    _write_table(
        TABLE_FAILURES_CSV, fails, ["dep", "entry_id", "failed_dimensions", "phraseology_score", "justification"]
    )
    return summary, dims, fails


def print_tables(rows: list[dict], summary: list, dims: list, fails: list) -> None:
    n_err = sum(1 for r in rows if r["error"])
    print("\n" + "=" * 78)
    print(f"  LLM-AS-JUDGE SUMMARY   ({len(rows)} entries, {n_err} errors)")
    print("=" * 78)

    print("\n[1] Pass rate + generation latency")
    print(f"{'Dep':<6} {'n':>4} {'n_pass':>7} {'pass%':>7} {'mean(s)':>8} {'p50(s)':>8} {'p95(s)':>8}")
    print("-" * 52)
    for s in summary:
        print(
            f"{s['dep']:<6} {s['n']:>4} {s['n_pass']:>7} {s['pass_rate_pct']:>6.1f}% "
            f"{s['latency_mean_s']:>8.2f} {s['latency_p50_s']:>8.2f} {s['latency_p95_s']:>8.2f}"
        )

    print("\n[2] Per-dimension pass rates (N/A excluded)")
    print(f"{'Dep':<6} {'values%':>8} {'complete%':>10} {'no-halluc%':>11} {'phr_mean':>9} {'phr>=4%':>8}")
    print("-" * 56)
    for d in dims:
        print(
            f"{d['dep']:<6} {d['values_correct_pass_pct']:>7.1f}% "
            f"{d['completeness_pass_pct']:>9.1f}% {d['no_hallucination_pass_pct']:>10.1f}% "
            f"{d['phraseology_mean']:>9.2f} {d['phraseology_p5_pct']:>7.1f}%"
        )

    print(f"\n[3] Failures catalogue ({len(fails)} entries)")
    if not fails:
        print("  (none)")
    for fr in fails[:40]:
        print(f"  {fr['dep']} {fr['entry_id']:<9} [{fr['failed_dimensions'] or '-'}] {fr['justification']}")
    if len(fails) > 40:
        print(f"  ... and {len(fails) - 40} more (see {TABLE_FAILURES_CSV})")


def write_all(rows: list[dict]) -> None:
    write_full(rows)
    write_review(rows)
    summary, dims, fails = write_tables(rows)
    print_tables(rows, summary, dims, fails)


# --------------------------------------------------------------------------- #
# Self-test: 2 judge calls, no agent calls
# --------------------------------------------------------------------------- #
_SELFTEST_ATC = (
    "Ryanair four seven three, cleared to Dublin via the BELEN one GOLF "
    "departure, initial climb five thousand feet, squawk two three four one, "
    "QNH one zero one three, runway three two left."
)
_SELFTEST_EXPECTED = (
    "Cleared to Dublin via BELEN one GOLF, initial climb five thousand, "
    "squawk two three four one, QNH one zero one three, runway three two "
    "left, Ryanair four seven three."
)
_SELFTEST_STRUCT = (
    '{"squawk": 2341, "initial_altitude": 5000, '
    '"instrumental_departure": "BELEN1G", "runway_in_use": "32L", '
    '"altimeter": 1013, "destination_icao": "EIDW"}'
)


def selftest(judge_model: str) -> int:
    print(f"Self-test (judge model: {judge_model}) - 2 calls, no agents.\n")
    cases = [
        ("correct readback", _SELFTEST_EXPECTED, "PASS", None),
        (
            "corrupted squawk+runway",
            "Cleared to Dublin via BELEN one GOLF, initial climb five thousand, "
            "squawk nine nine nine nine, QNH one zero one three, runway two seven right, "
            "Ryanair four seven three.",
            "FAIL",
            "values_correct",
        ),
    ]
    ok = True
    for label, reply, want_overall, want_fail_dim in cases:
        verdict, jlat, jerr = judge_reply(
            "DEL", _SELFTEST_ATC, _SELFTEST_EXPECTED, reply, _SELFTEST_STRUCT, judge_model
        )
        if jerr:
            print(f"  [{label}] JUDGE ERROR: {jerr}")
            ok = False
            continue
        got_overall = verdict.get("overall")
        got_vc = verdict.get("values_correct")
        print(f"  [{label}] ({jlat}s)")
        print(
            f"      overall={got_overall} values_correct={got_vc} "
            f"completeness={verdict.get('completeness')} "
            f"no_hallucination={verdict.get('no_hallucination')} "
            f"phraseology={verdict.get('phraseology_score')}"
        )
        print(f"      justificacion: {verdict.get('justification')}")
        exp_ok = got_overall == want_overall
        if want_fail_dim:
            exp_ok = exp_ok and verdict.get(want_fail_dim) == "FAIL"
        print(
            f"      -> expected overall={want_overall}"
            f"{f', {want_fail_dim}=FAIL' if want_fail_dim else ''}: "
            f"{'OK' if exp_ok else 'UNEXPECTED'}\n"
        )
        ok = ok and exp_ok
    print("SELF-TEST:", "PASS" if ok else "FAIL (unexpected verdicts, review rubric)")
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
def _parse_deps(spec: str) -> list[str]:
    wanted = [d.strip().upper() for d in spec.split(",") if d.strip()]
    return [d for d in ORDER if d in wanted] or list(ORDER)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=0, help="Only the first N entries per dependency (0 = all).")
    ap.add_argument("--deps", default="del,gnd,twr", help="Comma-separated subset of del,gnd,twr.")
    ap.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL, help=f"Judge model (default {DEFAULT_JUDGE_MODEL}).")
    ap.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_S,
        help=f"Per-agent-request timeout in seconds (default {DEFAULT_TIMEOUT_S}).",
    )
    ap.add_argument(
        "--rejudge", metavar="CSV", default="", help="Re-run only the judge phase from a previous full CSV."
    )
    ap.add_argument(
        "--selftest", action="store_true", help="2 hardcoded judge calls (expected PASS + FAIL); no agent calls."
    )
    args = ap.parse_args()

    # Spanish justifications contain accented characters; keep a cp1252 console
    # from raising UnicodeEncodeError when printing the failures catalogue.
    try:
        import sys

        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

    load_dotenv_into_environ()
    deps = _parse_deps(args.deps)

    if args.selftest:
        return selftest(args.judge_model)

    t0 = time.perf_counter()
    if args.rejudge:
        rows = run_rejudge(Path(args.rejudge), deps, args.limit, args.judge_model)
    else:
        rows = run_full(deps, args.limit, args.judge_model, args.timeout)

    if not rows:
        print("No rows produced - nothing to write.")
        return 1

    print(f"\nCollected {len(rows)} rows in {time.perf_counter() - t0:.0f}s.")
    write_all(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
