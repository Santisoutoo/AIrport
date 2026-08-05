"""Semantic validation of the three ATC agents (DEL, GND, TWR).

For each corpus entry, sends the ATC message to the corresponding Cloud Run
agent with a *new* session_id, extracts the expected field values from the
ATC text (regex-based phonetic decoding), and compares them against what the
agent returned.

Three workers (one per dependency) run in parallel; calls within a
dependency are serial.

Outputs (under agents_evaluation/output/):
  - agent_validation.jsonl          — one line per entry, full dump for inspection
  - agent_validation_summary.csv    — one row per entry, per-field OK/FAIL columns

CLI:
  python validate_agents.py [--timeout SECONDS] [--no-call]
  Env:  VALIDATE_TIMEOUT_S=180

Reads endpoints from .env (DEL_AGENT_URL, GND_AGENT_URL, TWR_AGENT_URL).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import socket
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from benchmark_agents import (
    REQUIRED_FIELDS,
    STRUCTURED_KEY,
    SUFFIX,
    load_env_urls,
    parse_corpus,
)

CORPUS_DIR = Path("agents_evaluation/corpus_wer")
OUT_DIR = Path("agents_evaluation/output")
JSONL_OUT = OUT_DIR / "agent_validation.jsonl"
CSV_OUT = OUT_DIR / "agent_validation_summary.csv"

DEFAULT_TIMEOUT_S = int(os.environ.get("VALIDATE_TIMEOUT_S", "180"))
RETRY_SLEEP_S = 5

PHONETIC_DIGIT = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "niner": 9,
}
DIGIT_WORDS_RE = r"(?:zero|one|two|three|four|five|six|seven|eight|nine|niner)"

PHONETIC_LETTER = {
    "alpha": "A",
    "bravo": "B",
    "charlie": "C",
    "delta": "D",
    "echo": "E",
    "foxtrot": "F",
    "golf": "G",
    "hotel": "H",
    "india": "I",
    "juliet": "J",
    "kilo": "K",
    "lima": "L",
    "mike": "M",
    "november": "N",
    "oscar": "O",
    "papa": "P",
    "quebec": "Q",
    "romeo": "R",
    "sierra": "S",
    "tango": "T",
    "uniform": "U",
    "victor": "V",
    "whiskey": "W",
    "xray": "X",
    "yankee": "Y",
    "zulu": "Z",
}
LETTER_WORDS_RE = (
    r"(?:alpha|bravo|charlie|delta|echo|foxtrot|golf|hotel|india|juliet|kilo|"
    r"lima|mike|november|oscar|papa|quebec|romeo|sierra|tango|uniform|victor|"
    r"whiskey|xray|yankee|zulu)"
)

RUNWAY_SIDE = {"left": "L", "right": "R", "center": "C", "centre": "C"}

# City → ICAO. Only unambiguous mappings seen in the corpus.
CITY_ICAO = {
    "Dublin": "EIDW",
    "Barcelona": "LEBL",
    "Frankfurt": "EDDF",
    "London Heathrow": "EGLL",
    "London Gatwick": "EGKK",
    "London Stansted": "EGSS",
    "Zurich": "LSZH",
    "Paris Charles de Gaulle": "LFPG",
    "Palma de Mallorca": "LEPA",
    "Oslo": "ENGM",
    "Lisbon": "LPPT",
    "Amsterdam": "EHAM",
    "Helsinki": "EFHK",
    "Munich": "EDDM",
    "Bilbao": "LEBB",
    "Manchester": "EGCC",
    "Cork": "EICK",
    "Bergen": "ENBR",
    "Budapest": "LHBP",
    "Madrid": "LEMD",
    "Rome Fiumicino": "LIRF",
    "Sevilla": "LEZL",
    "Trondheim": "ENVA",
    "Vienna": "LOWW",
    "Stockholm": "ESSA",
    "Warsaw": "EPWA",
    "Zagreb": "LDZA",
    "Valencia": "LEVC",
    "Geneva": "LSGG",
    "Bristol": "EGGD",
    "Alicante": "LEAL",
    "Bucharest": "LROP",
    "Birmingham": "EGBB",
    "Naples": "LIRN",
    "Marseille": "LFML",
    "Porto": "LPPR",
    "Rotterdam": "EHRD",
}


def _phonetic_to_int(words: list[str]) -> int | None:
    digits = [PHONETIC_DIGIT[w.lower()] for w in words if w.lower() in PHONETIC_DIGIT]
    if not digits:
        return None
    return int("".join(str(d) for d in digits))


def phonetic_digits(text: str) -> int | None:
    return _phonetic_to_int(text.split())


def phonetic_thousands(text: str) -> int | None:
    words = text.lower().split()
    if "thousand" not in words:
        return None
    idx = words.index("thousand")
    multiplier = _phonetic_to_int(words[:idx])
    if multiplier is None:
        return None
    return multiplier * 1000


def runway_code(text: str) -> str | None:
    words = text.lower().split()
    digits, side = [], ""
    for w in words:
        if w in PHONETIC_DIGIT:
            digits.append(str(PHONETIC_DIGIT[w]))
        elif w in RUNWAY_SIDE:
            side = RUNWAY_SIDE[w]
    if not digits:
        return None
    return "".join(digits) + side


def sid_code(name: str, ord_word: str, letter_word: str) -> str | None:
    o = ord_word.lower()
    l = letter_word.lower()
    if o not in PHONETIC_DIGIT or l not in PHONETIC_LETTER:
        return None
    return f"{name.upper()}{PHONETIC_DIGIT[o]}{PHONETIC_LETTER[l]}"


def extract_destination(text: str) -> str | None:
    # Greedy match up to 4 capitalised words.
    m = re.search(r"cleared to ([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})", text)
    if not m:
        return None
    parts = m.group(1).strip().split()
    for length in range(len(parts), 0, -1):
        prefix = " ".join(parts[:length])
        if prefix in CITY_ICAO:
            return CITY_ICAO[prefix]
    return None


def extract_ground_truth(dep: str, atc_text: str, expected_readback: str) -> dict:
    """Extract expected field values from ATC + readback combined.

    Some corpus entries put the clearance values in the controller line (>);
    others (pilot-initiated requests) put them in the expected response (<).
    We concatenate both and let the regex match wherever the values appear.
    """
    text = atc_text + " " + expected_readback
    gt: dict = {}

    runway_re = (
        rf"runway ((?:{DIGIT_WORDS_RE})\s+(?:{DIGIT_WORDS_RE})"
        rf"(?:\s+(?:left|right|center|centre))?)"
    )

    if dep == "DEL":
        m = re.search(rf"squawk ((?:{DIGIT_WORDS_RE}\s+){{3}}{DIGIT_WORDS_RE})", text, re.I)
        gt["squawk"] = phonetic_digits(m.group(1)) if m else None

        m = re.search(
            rf"initial climb ((?:{DIGIT_WORDS_RE}\s+)*{DIGIT_WORDS_RE}\s+thousand)",
            text,
            re.I,
        )
        gt["initial_altitude"] = phonetic_thousands(m.group(1)) if m else None

        m = re.search(
            rf"via (?:the\s+)?([A-Za-z]+)\s+({DIGIT_WORDS_RE})\s+({LETTER_WORDS_RE})\s+departure",
            text,
            re.I,
        )
        gt["instrumental_departure"] = sid_code(m.group(1), m.group(2), m.group(3)) if m else None

        m = re.search(runway_re, text, re.I)
        gt["runway_in_use"] = runway_code(m.group(1)) if m else None

        m = re.search(rf"QNH ((?:{DIGIT_WORDS_RE}\s+){{3}}{DIGIT_WORDS_RE})", text, re.I)
        gt["altimeter"] = phonetic_digits(m.group(1)) if m else None

        gt["destination_icao"] = extract_destination(text)

    elif dep == "GND":
        m = re.search(runway_re, text, re.I)
        gt["runway_in_use"] = runway_code(m.group(1)) if m else None

    elif dep == "TWR":
        m = re.search(runway_re, text, re.I)
        gt["runway_in_use"] = runway_code(m.group(1)) if m else None

    return gt


def normalize(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value.upper().strip().replace(" ", "")
    if isinstance(value, float):
        if math.isfinite(value) and value == int(value):
            return int(value)
        return value
    return value


def compare_fields(dep: str, ground_truth: dict, agent_block: dict | None) -> dict:
    results = {}
    if agent_block is None:
        for field in ground_truth:
            results[field] = {
                "expected": ground_truth.get(field),
                "returned": None,
                "match": None,
                "reason": "acknowledgement",
            }
        return results
    for field, expected in ground_truth.items():
        returned = agent_block.get(field)
        if expected is None:
            results[field] = {
                "expected": None,
                "returned": returned,
                "match": None,
                "reason": "no_ground_truth",
            }
        elif returned in (None, ""):
            results[field] = {
                "expected": expected,
                "returned": returned,
                "match": False,
                "reason": "missing",
            }
        else:
            ok = normalize(expected) == normalize(returned)
            results[field] = {
                "expected": expected,
                "returned": returned,
                "match": ok,
                "reason": "ok" if ok else "mismatch",
            }
    return results


def call_agent_with_retry(url: str, session_id: str, message: str, timeout_s: int):
    payload = json.dumps({"session_id": session_id, "message": message}).encode("utf-8")

    def _attempt():
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            elapsed = time.perf_counter() - t0
            body = resp.read().decode("utf-8")
            return resp.status, elapsed, json.loads(body), ""

    try:
        return _attempt()
    except urllib.error.HTTPError as e:
        return e.code, 0.0, None, f"HTTPError: {e}"
    except (socket.timeout, urllib.error.URLError, TimeoutError):
        time.sleep(RETRY_SLEEP_S)
        try:
            return _attempt()
        except Exception as e2:
            return -1, 0.0, None, f"retry_failed: {type(e2).__name__}: {e2}"
    except Exception as e:
        return -1, 0.0, None, f"{type(e).__name__}: {e}"


def run_dependency(dep: str, base_url: str, timeout_s: int, no_call: bool) -> list[dict]:
    if not base_url:
        print(f"[{dep}] skip - no endpoint configured", flush=True)
        return []
    full_url = base_url.rstrip("/") + SUFFIX[dep]
    corpus_path = CORPUS_DIR / dep.lower() / f"corpus_wer_{dep.lower()}.txt"
    entries = parse_corpus(corpus_path)
    print(f"[{dep}] {len(entries)} entries -> {full_url}", flush=True)

    rows: list[dict] = []
    struct_key = STRUCTURED_KEY[dep]
    for i, (entry_id, atc_text, pilot_text) in enumerate(entries, 1):
        gt = extract_ground_truth(dep, atc_text, pilot_text)
        session_id = f"val-{dep.lower()}-{entry_id}-{uuid.uuid4().hex[:6]}"

        if no_call:
            status, lat, resp, err = 200, 0.0, {struct_key: None, "reply": "(dry-run)"}, ""
        else:
            status, lat, resp, err = call_agent_with_retry(full_url, session_id, atc_text, timeout_s)

        schema_valid = (status == 200) and (resp is not None)
        agent_block = resp.get(struct_key) if isinstance(resp, dict) else None
        bloque_completo = True
        if schema_valid and agent_block is not None:
            for f in REQUIRED_FIELDS[dep]:
                v = agent_block.get(f)
                if v is None or v == "":
                    bloque_completo = False
                    break
        field_results = compare_fields(dep, gt, agent_block) if schema_valid else {}

        rows.append(
            {
                "dep": dep,
                "entry_id": entry_id,
                "session_id": session_id,
                "atc_text": atc_text,
                "expected_readback": pilot_text,
                "ground_truth": gt,
                "agent_response": resp,
                "structured_block": agent_block,
                "status": status,
                "latency_s": round(lat, 3),
                "schema_valid": schema_valid,
                "bloque_completo": bloque_completo,
                "field_results": field_results,
                "error": err,
            }
        )
        mark = "OK " if schema_valid else "ERR"
        print(f"[{dep}] [{i:3d}/{len(entries)}] {entry_id} {mark} ({lat:5.1f}s)", flush=True)
    return rows


def write_jsonl(rows: list[dict], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_summary_csv(rows: list[dict], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    all_fields: set[str] = set()
    for r in rows:
        all_fields.update(r["ground_truth"].keys())
    all_fields_sorted = sorted(all_fields)
    headers = (
        ["dep", "entry_id", "status", "latency_s", "schema_valid", "bloque_completo"]
        + [f"match_{f}" for f in all_fields_sorted]
        + ["n_ok", "n_total", "n_unknown", "error"]
    )
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            row = {
                "dep": r["dep"],
                "entry_id": r["entry_id"],
                "status": r["status"],
                "latency_s": r["latency_s"],
                "schema_valid": r["schema_valid"],
                "bloque_completo": r["bloque_completo"],
                "error": r["error"],
            }
            n_ok = n_total = n_unknown = 0
            for field in all_fields_sorted:
                fr = r["field_results"].get(field)
                if fr is None:
                    row[f"match_{field}"] = ""
                    continue
                m = fr.get("match")
                if m is True:
                    row[f"match_{field}"] = "OK"
                    n_ok += 1
                    n_total += 1
                elif m is False:
                    row[f"match_{field}"] = "FAIL"
                    n_total += 1
                else:
                    row[f"match_{field}"] = fr.get("reason", "-")
                    n_unknown += 1
            row["n_ok"] = n_ok
            row["n_total"] = n_total
            row["n_unknown"] = n_unknown
            w.writerow(row)


def print_summary(rows: list[dict]):
    print()
    deps = ("DEL", "GND", "TWR")
    fields_by_dep: dict[str, set[str]] = {d: set() for d in deps}
    for r in rows:
        if r["dep"] in fields_by_dep:
            fields_by_dep[r["dep"]].update(r["ground_truth"].keys())
    all_fields = sorted(set().union(*fields_by_dep.values()))

    header = f"{'Dep':<5} {'n':>4} {'%schema':>9} {'%bloque':>9}"
    for f in all_fields:
        header += f" {'%' + f:>14}"
    print(header)
    print("-" * len(header))

    for dep in deps:
        sub = [r for r in rows if r["dep"] == dep]
        n = len(sub)
        if n == 0:
            continue
        schema_ok = sum(1 for r in sub if r["schema_valid"])
        bloque_ok = sum(1 for r in sub if r["bloque_completo"])
        line = f"{dep:<5} {n:>4} {100 * schema_ok / n:>8.1f}% {100 * bloque_ok / n:>8.1f}%"
        for field in all_fields:
            if field not in fields_by_dep[dep]:
                line += f" {'-':>14}"
                continue
            ok = total = 0
            for r in sub:
                fr = r["field_results"].get(field)
                if fr is None:
                    continue
                m = fr.get("match")
                if m is True:
                    ok += 1
                    total += 1
                elif m is False:
                    total += 1
            if total:
                line += f" {100 * ok / total:>13.1f}%"
            else:
                line += f" {'n/a':>14}"
        print(line)


def preview_ground_truth(n: int = 3):
    """Print the first n ground-truth extractions per dep, for sanity checking."""
    print("\nGround truth preview (first 3 entries per dep):")
    for dep in ("DEL", "GND", "TWR"):
        corpus_path = CORPUS_DIR / dep.lower() / f"corpus_wer_{dep.lower()}.txt"
        if not corpus_path.exists():
            continue
        entries = parse_corpus(corpus_path)[:n]
        for entry_id, atc, pilot in entries:
            gt = extract_ground_truth(dep, atc, pilot)
            print(f"  [{dep}] {entry_id}: {gt}")
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_S,
        help=f"Per-request timeout in seconds (default {DEFAULT_TIMEOUT_S}; override with env VALIDATE_TIMEOUT_S)",
    )
    ap.add_argument(
        "--no-call", action="store_true", help="Skip agent calls; exercise extraction/comparison pipeline only."
    )
    args = ap.parse_args()

    urls = load_env_urls()
    print("Endpoints:")
    for d, u in urls.items():
        print(f"  {d}: {u or '[NOT SET]'}")
    print(f"Timeout per request: {args.timeout}s")
    if args.no_call:
        print("DRY RUN - no agent calls will be made.")

    preview_ground_truth()

    all_rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {
            ex.submit(run_dependency, dep, urls[dep], args.timeout, args.no_call): dep for dep in ("DEL", "GND", "TWR")
        }
        for fut in as_completed(futures):
            dep = futures[fut]
            try:
                rows = fut.result()
            except Exception as e:
                print(f"[{dep}] worker crashed: {type(e).__name__}: {e}", flush=True)
                rows = []
            all_rows.extend(rows)
            print(f"[{dep}] worker done ({len(rows)} rows).", flush=True)

    order = {"DEL": 0, "GND": 1, "TWR": 2}
    all_rows.sort(key=lambda r: (order.get(r["dep"], 99), r["entry_id"]))

    write_jsonl(all_rows, JSONL_OUT)
    write_summary_csv(all_rows, CSV_OUT)
    print(f"\nWrote: {JSONL_OUT}")
    print(f"Wrote: {CSV_OUT}")
    print_summary(all_rows)


if __name__ == "__main__":
    main()
