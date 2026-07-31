"""Benchmark deployed ASR Cloud Run services against a voice dataset.

Transcribes every .wav under an audio root (subfolders del/gnd/twr), compares the
raw transcription against the corpus ATC reference (the "> " lines) and writes a
per-request CSV trace plus a printed summary (WER with S/D/I breakdown, latency,
cost). Audios are REFERENCED from an external path (default: the
pilot-readback-corpus repo); nothing is copied into this repo.

Stdlib only (urllib) so it runs without extra deps; WER is computed with a small
word-level Levenshtein aligner (S/D/I) — no jiwer required.

Example:
  python benchmark_asr.py \
    --asr-url https://asr-medium-c2-xt7obtivma-ew.a.run.app \
    --model medium --tier c2 --cost-per-h 0.21 --workers 4 \
    --audio-root "C:/Users/santi/Documents/personal_projects/pilot-readback-corpus/output" \
    --ref-root   "C:/Users/santi/Documents/personal_projects/pilot-readback-corpus"
"""
import argparse
import csv
import json
import os
import random
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DEPS = ["del", "gnd", "twr"]


# --------------------------------------------------------------------------- #
# Reference canonicalisation + session entity extraction
#
# When --context session is used, the service post-processor fuzzy-matches the
# raw transcription against per-position vocabularies (callsigns + SIDs). We
# derive those vocabularies from the corpus references and also canonicalise
# each reference for a fair wer_post ("Ryanair four seven three" -> "RYR473",
# "via the BELEN one GOLF departure" -> "via BELEN1G departure").
#
# The service's own core.postprocess is reused when importable, so the
# benchmark canonicalises exactly like production; but the script must never
# hard-depend on the service stack (it may not be built yet, or run outside the
# container). If the import fails we fall back to a small local canonicaliser
# built from the same NATO phonetic vocabularies.
# --------------------------------------------------------------------------- #
_SERVICE_DIR = Path(__file__).resolve().parent.parent / "services" / "asr_service"

_PHON_DIGIT = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "niner": "9",
}
_PHON_LETTER = {
    "alpha": "A", "bravo": "B", "charlie": "C", "delta": "D", "echo": "E",
    "foxtrot": "F", "golf": "G", "hotel": "H", "india": "I", "juliet": "J",
    "kilo": "K", "lima": "L", "mike": "M", "november": "N", "oscar": "O",
    "papa": "P", "quebec": "Q", "romeo": "R", "sierra": "S", "tango": "T",
    "uniform": "U", "victor": "V", "whiskey": "W", "xray": "X", "yankee": "Y",
    "zulu": "Z",
}

# Airline callword -> ICAO, keyed by the *spoken* name as it appears in the
# corpus (lower-case). Extended/overridden by the service's AIRLINE_ICAO when
# the import below succeeds.
_FALLBACK_ICAO = {
    "ryanair": "RYR", "iberia": "IBE", "lufthansa": "DLH", "speedbird": "BAW",
    "swiss": "SWR", "easyjet": "EZY", "vueling": "VLG", "aer lingus": "EIN",
    "norwegian": "NAX", "tap": "TAP", "transavia": "TRA", "volotea": "VOE",
    "finnair": "FIN", "klm": "KLM", "turkish": "THY", "condor": "CFG",
    "wizz air": "WZZ", "jet2": "EXS", "air france": "AFR", "brussels": "BEL",
    "austrian": "AUA", "sas": "SAS", "alitalia": "AZA", "lot": "LOT",
    "croatia": "CTN", "pegasus": "PGT",
}

_HAVE_SERVICE_POSTPROCESS = False
_svc_normalize_reference = None
_svc_airline_icao: dict[str, str] = {}
try:
    if str(_SERVICE_DIR) not in sys.path:
        sys.path.insert(0, str(_SERVICE_DIR))
    from core.postprocess import AIRLINE_ICAO as _svc_airline_icao  # type: ignore
    from core.postprocess import normalize_reference as _svc_normalize_reference  # type: ignore
    _HAVE_SERVICE_POSTPROCESS = True
except Exception:  # noqa: BLE001 - service stack is optional
    _svc_normalize_reference = None
    _svc_airline_icao = {}

# Corpus spellings first, service entries layered on top (service is the source
# of truth for ICAO codes when present).
AIRLINE_ICAO = dict(_FALLBACK_ICAO)
for _k, _v in (_svc_airline_icao or {}).items():
    AIRLINE_ICAO[str(_k).lower()] = _v

# Regex fragments built from the vocabularies (non-capturing digit/letter runs)
_NUM_WORD = "|".join(_PHON_DIGIT)
_LET_WORD = "|".join(_PHON_LETTER)
_NW = "(?:" + _NUM_WORD + ")"
_LW = "(?:" + _LET_WORD + ")"
# Longest airline names first so "aer lingus" wins over any 1-word prefix.
_AIRLINE_ALT = "|".join(
    re.escape(k) for k in sorted(AIRLINE_ICAO, key=len, reverse=True))

_STATION_RE = re.compile(
    r"^\s*santiago\s+(?:delivery|ground|tower)\s*,?\s*", re.IGNORECASE)
_CS_RE = re.compile(
    r"(" + _AIRLINE_ALT + r")\s+"
    r"((?:(?:" + _NW + r"|" + _LW + r")\s+){1,4}(?:" + _NW + r"|" + _LW + r"))",
    re.IGNORECASE)
_SID_RE = re.compile(
    r"\bvia\s+(?:the\s+)?([A-Za-z]{3,})\s+(" + _NUM_WORD + r")\s+("
    + _LET_WORD + r")\s+departure\b", re.IGNORECASE)
_FREQ_RE = re.compile(
    r"\b(" + _NW + r"(?:\s+" + _NW + r")*)\s+decimal\s+("
    + _NW + r"(?:\s+" + _NW + r")*)\b", re.IGNORECASE)
_RWY_RE = re.compile(
    r"\brunway\s+(" + _NW + r")\s+(" + _NW + r")(?:\s+(left|right|centre|center))?\b",
    re.IGNORECASE)
_SQ_RE = re.compile(
    r"\b(squawk|QNH)\s+(" + _NW + r"(?:\s+" + _NW + r"){3})\b", re.IGNORECASE)
_FL_RE = re.compile(
    r"\bflight level\s+(" + _NW + r"(?:\s+" + _NW + r"){1,2})\b", re.IGNORECASE)
_TH_RE = re.compile(
    r"\b(" + _NW + r"(?:\s+" + _NW + r")*)\s+thousand\b", re.IGNORECASE)
_RUNWAY_SIDE = {"left": "L", "right": "R", "centre": "C", "center": "C"}

# Extra out-of-corpus entities so the fuzzy matcher has to discriminate.
CS_DISTRACTORS = ["VLG32A", "EZY1102", "AEA905"]
SID_DISTRACTORS = ["ROTEX2B", "MANLU1K"]


def _phon_code(spoken: str) -> str:
    """Compact NATO phonetic run -> alnum code ("four seven three" -> "473")."""
    out = []
    for w in spoken.split():
        wl = w.lower()
        if wl in _PHON_DIGIT:
            out.append(_PHON_DIGIT[wl])
        elif wl in _PHON_LETTER:
            out.append(_PHON_LETTER[wl])
    return "".join(out)


def _digits(spoken: str) -> str:
    return "".join(_PHON_DIGIT[w.lower()] for w in spoken.split()
                   if w.lower() in _PHON_DIGIT)


def extract_callsign(ref: str) -> str:
    """ICAO callsign addressed at the head of a reference, or "" if none."""
    head = _STATION_RE.sub("", ref or "").split(",")[0].strip()
    m = _CS_RE.match(head)
    if not m:
        return ""
    icao = AIRLINE_ICAO.get(m.group(1).lower(), "")
    code = _phon_code(m.group(2))
    return f"{icao}{code}" if icao and code else ""


def extract_sids(text: str) -> list[str]:
    """All canonical SIDs in a text ("via the BELEN one GOLF departure")."""
    out = []
    for m in _SID_RE.finditer(text or ""):
        d = _PHON_DIGIT.get(m.group(2).lower(), "")
        l = _PHON_LETTER.get(m.group(3).lower(), "")
        if d and l:
            out.append(f"{m.group(1).upper()}{d}{l}")
    return out


def extract_sid(text: str) -> str:
    sids = extract_sids(text)
    return sids[0] if sids else ""


def _cs_sub(m: re.Match) -> str:
    icao = AIRLINE_ICAO.get(m.group(1).lower())
    code = _phon_code(m.group(2))
    return f"{icao}{code}" if icao and code else m.group(0)


def _sid_sub(m: re.Match) -> str:
    d = _PHON_DIGIT.get(m.group(2).lower(), "")
    l = _PHON_LETTER.get(m.group(3).lower(), "")
    return f"via {m.group(1).upper()}{d}{l} departure" if d and l else m.group(0)


def _rwy_sub(m: re.Match) -> str:
    d = _PHON_DIGIT.get(m.group(1).lower(), "") + _PHON_DIGIT.get(m.group(2).lower(), "")
    return "runway " + d + _RUNWAY_SIDE.get((m.group(3) or "").lower(), "")


def _fallback_normalize_reference(text: str) -> str:
    """Minimal local canonicaliser used when core.postprocess is unavailable."""
    if not text:
        return ""
    t = text
    t = _FREQ_RE.sub(lambda m: _digits(m.group(1)) + "." + _digits(m.group(2)), t)
    t = _SQ_RE.sub(lambda m: m.group(1) + " " + _digits(m.group(2)), t)
    t = _RWY_RE.sub(_rwy_sub, t)
    t = _FL_RE.sub(lambda m: "FL" + _digits(m.group(1)), t)
    t = _TH_RE.sub(
        lambda m: str(int(_digits(m.group(1))) * 1000) if _digits(m.group(1)) else m.group(0), t)
    t = _SID_RE.sub(_sid_sub, t)
    t = _CS_RE.sub(_cs_sub, t)
    return t


def normalize_reference(text: str) -> str:
    """Canonicalise a reference (service impl if available, else local fallback)."""
    if _svc_normalize_reference is not None:
        try:
            return _svc_normalize_reference(text)
        except Exception:  # noqa: BLE001
            pass
    return _fallback_normalize_reference(text)


def build_session_lists(refs: list[str]) -> tuple[list[str], list[str]]:
    """Unique callsigns + SIDs across all references, plus a few distractors."""
    cs, sids = set(), set()
    for ref in refs:
        c = extract_callsign(ref)
        if c:
            cs.add(c)
        sids.update(extract_sids(ref))
    callsigns = sorted(cs) + CS_DISTRACTORS
    sid_list = sorted(sids) + SID_DISTRACTORS
    return callsigns, sid_list


# --------------------------------------------------------------------------- #
# Corpus parsing (same format as agents_evaluation/evaluate_wer.load_corpus)
# --------------------------------------------------------------------------- #
def load_corpus(path: Path) -> dict[str, dict]:
    corpus, cid, ref, rb = {}, None, None, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            cid = line[1:-1]; ref = rb = None
        elif line.startswith("> ") and cid:
            ref = line[2:]
        elif line.startswith("< ") and cid:
            rb = line[2:]; corpus[cid] = {"ref": ref, "readback": rb}
    return corpus


# --------------------------------------------------------------------------- #
# Normalisation + word-level WER (S/D/I)
# --------------------------------------------------------------------------- #
_PUNCT = re.compile(r"[^\w\s]")


def normalize(text: str) -> list[str]:
    if not text:
        return []
    text = text.lower()
    text = _PUNCT.sub(" ", text)
    return text.split()


def wer_breakdown(ref: str, hyp: str) -> dict:
    """Levenshtein over word lists -> {wer, sub, dele, ins, n_ref}."""
    r, h = normalize(ref), normalize(hyp)
    n, m = len(r), len(h)
    # dp[i][j] = edit distance between r[:i] and h[:j]
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    # backtrace for S/D/I
    i, j, sub, dele, ins = n, m, 0, 0, 0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + (0 if r[i - 1] == h[j - 1] else 1):
            if r[i - 1] != h[j - 1]:
                sub += 1
            i, j = i - 1, j - 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            dele += 1; i -= 1
        else:
            ins += 1; j -= 1
    werv = (sub + dele + ins) / n if n else 0.0
    return {"wer": werv, "sub": sub, "dele": dele, "ins": ins, "n_ref": n}


# --------------------------------------------------------------------------- #
# Transcription over HTTP (multipart, stdlib)
# --------------------------------------------------------------------------- #
# Transient statuses worth retrying: Cloud Run returns 429 when it can't scale
# fast enough (cold burst) and 500/502/503 on instance churn.
_RETRY_CODES = {429, 500, 502, 503}


def transcribe(api_url: str, wav_path: Path, context_mode: str,
               session_callsigns: str = "", session_sids: str = "",
               max_retries: int = 5) -> tuple[dict, float]:
    boundary = uuid.uuid4().hex
    audio = wav_path.read_bytes()
    body = bytearray()

    def field(name, value):
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(f"{value}\r\n".encode())

    field("context_mode", context_mode)
    # Session vocabularies (CSV strings). The service only consumes them in
    # "session" mode; sending them otherwise is harmless, so we gate on content.
    if session_callsigns:
        field("session_callsigns", session_callsigns)
    if session_sids:
        field("session_sids", session_sids)
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="audio"; filename="{wav_path.name}"\r\n'.encode())
    body.extend(b"Content-Type: audio/wav\r\n\r\n")
    body.extend(audio)
    body.extend(f"\r\n--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        api_url, data=bytes(body), method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            t0 = time.perf_counter()
            with urllib.request.urlopen(req, timeout=600) as r:
                data = json.loads(r.read())
            return data, time.perf_counter() - t0
        except urllib.error.HTTPError as e:
            last_exc = e
            if e.code not in _RETRY_CODES:
                raise
        except urllib.error.URLError as e:
            last_exc = e
        # exponential backoff with jitter (2s, 4s, 8s, ... capped at 30s)
        time.sleep(min(2 ** (attempt + 1) + random.random(), 30))
    raise last_exc  # type: ignore[misc]


def wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path)) as w:
            return w.getnframes() / w.getframerate()
    except Exception:
        return 0.0


# --------------------------------------------------------------------------- #
def _entity_columns(ref: str, final: str, data: dict) -> dict:
    """Per-row canonicalisation + entity-recovery metrics.

    wer_post is measured against the *canonicalised* reference (so "RYR473" in
    the transcription scores against "RYR473" in the reference, not against the
    spoken "Ryanair four seven three"). cs/sid correctness checks whether the
    canonical entity survives as an exact token in the final transcription.
    """
    ref_norm = normalize_reference(ref)
    wp = wer_breakdown(ref_norm, final)
    cs = extract_callsign(ref)
    sid = extract_sid(ref)
    hyp_tokens = set(normalize(final))
    return {
        "ref_normalized": ref_norm,
        "wer_post": round(wp["wer"], 4),
        "cs_canonical": cs,
        "cs_correct": bool(cs) and cs.lower() in hyp_tokens,
        "sid_canonical": sid,
        "sid_correct": (sid.lower() in hyp_tokens) if sid else "",
        "llm_applied": data.get("llm_applied", False),
        "llm_latency_s": data.get("llm_latency_s", ""),
    }


def _blank_row(dep, wav, ref, ctx):
    return {
        "audio_id": wav.stem, "dep": dep, "wav": wav.name,
        "audio_dur_s": round(wav_duration(wav), 2), "ref": ref,
        "ref_normalized": "", "context_mode": ctx,
        "raw_transcription": "", "final_transcription": "",
        "duration_s": "", "latency_client_s": "",
        "wer_raw": "", "sub_raw": "", "del_raw": "", "ins_raw": "", "n_ref": "",
        "wer_post": "", "cs_canonical": "", "cs_correct": "",
        "sid_canonical": "", "sid_correct": "", "llm_applied": "", "llm_latency_s": "",
        "rtf": "", "cost_per_transcription": "", "http_status": "", "error": "",
    }


def run_one(api_url, dep, wav, ref, ctx, cost_per_h,
            session_callsigns="", session_sids="", dry_run=False):
    row = _blank_row(dep, wav, ref, ctx)
    if dry_run:
        # No service call: exercise the plumbing with hyp = ref (raw & final).
        dur = row["audio_dur_s"]
        wr = wer_breakdown(ref, ref)
        row.update({
            "raw_transcription": ref, "final_transcription": ref,
            "duration_s": dur, "latency_client_s": 0.0,
            "wer_raw": round(wr["wer"], 4), "sub_raw": wr["sub"], "del_raw": wr["dele"],
            "ins_raw": wr["ins"], "n_ref": wr["n_ref"], "http_status": 200,
        })
        row.update(_entity_columns(ref, ref, {}))
        if dur:
            row["rtf"] = round(dur / dur, 2)
            row["cost_per_transcription"] = round(cost_per_h / 3600.0 * dur, 6)
        return row
    try:
        data, wall = transcribe(api_url, wav, ctx, session_callsigns, session_sids)
        raw = data.get("raw_transcription") or ""
        final = data.get("transcription") or ""
        dur = data.get("duration_s")
        wr = wer_breakdown(ref, raw)
        row.update({
            "raw_transcription": raw, "final_transcription": final,
            "duration_s": round(dur, 3) if isinstance(dur, (int, float)) else "",
            "latency_client_s": round(wall, 3),
            "wer_raw": round(wr["wer"], 4), "sub_raw": wr["sub"], "del_raw": wr["dele"],
            "ins_raw": wr["ins"], "n_ref": wr["n_ref"],
            "http_status": 200,
        })
        row.update(_entity_columns(ref, final, data))
        if isinstance(dur, (int, float)) and row["audio_dur_s"]:
            row["rtf"] = round(dur / row["audio_dur_s"], 2)
            row["cost_per_transcription"] = round(cost_per_h / 3600.0 * dur, 6)
    except Exception as exc:  # noqa: BLE001
        row["error"] = str(exc)[:300]
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asr-url", default="",
                    help="Base Cloud Run URL (no path); not needed with --dry-run")
    ap.add_argument("--model", required=True)
    ap.add_argument("--tier", required=True)
    ap.add_argument("--cost-per-h", type=float, default=0.0)
    ap.add_argument("--context", default="generic", choices=["none", "generic", "session"])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--deps", default="del,gnd,twr")
    ap.add_argument(
        "--audio-root",
        default=os.getenv("ASR_BENCH_AUDIO_DIR",
                          r"C:/Users/santi/Documents/personal_projects/pilot-readback-corpus/output"))
    ap.add_argument(
        "--ref-root",
        default=r"C:/Users/santi/Documents/personal_projects/pilot-readback-corpus")
    ap.add_argument("--out", default="")
    ap.add_argument("--dry-run", action="store_true",
                    help="Build session lists + new columns without calling the "
                         "service (fills hyp=ref for a few audios, writes to a temp CSV)")
    args = ap.parse_args()

    api = args.asr_url.rstrip("/") + "/api/v1/asr/transcribe" if args.asr_url else ""
    audio_root, ref_root = Path(args.audio_root), Path(args.ref_root)
    deps = [d.strip() for d in args.deps.split(",") if d.strip()]

    # ---- per-dependency corpus + session vocabularies ----
    corpus_by_dep: dict[str, dict] = {}
    session_by_dep: dict[str, tuple[str, str]] = {}
    for dep in deps:
        ref_txt = ref_root / dep.upper() / f"corpus_wer_{dep}.txt"
        if not ref_txt.exists():
            print(f"[WARN] no ref for {dep}: {ref_txt}"); continue
        corpus = load_corpus(ref_txt)
        corpus_by_dep[dep] = corpus
        refs = [e["ref"] for e in corpus.values() if e.get("ref")]
        cs_list, sid_list = build_session_lists(refs)
        session_by_dep[dep] = (",".join(cs_list), ",".join(sid_list))

    if args.dry_run:
        return _run_dry(args, deps, audio_root, corpus_by_dep, session_by_dep)

    tasks = []
    for dep in deps:
        corpus = corpus_by_dep.get(dep)
        if not corpus:
            continue
        wavs = sorted((audio_root / dep).glob("*.wav"))
        for wav in wavs:
            ent = corpus.get(wav.stem)
            if not ent:
                print(f"[WARN] {wav.stem} not in corpus — skipping"); continue
            tasks.append((dep, wav, ent["ref"]))

    # Session vocabularies only travel to the service in "session" context.
    use_session = args.context == "session"
    print(f"Model={args.model} tier={args.tier}  {len(tasks)} audios  "
          f"ctx={args.context}  workers={args.workers}\n  {api}\n")

    rows, done, t0 = [], 0, time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {}
        for dep, wav, ref in tasks:
            cs_csv, sid_csv = session_by_dep.get(dep, ("", "")) if use_session else ("", "")
            futs[ex.submit(run_one, api, dep, wav, ref, args.context,
                           args.cost_per_h, cs_csv, sid_csv)] = wav
        for fut in as_completed(futs):
            row = fut.result(); rows.append(row); done += 1
            tag = row["error"] or f"wer_raw={row['wer_raw']}"
            print(f"  [{done}/{len(tasks)}] {row['audio_id']}  {tag}")

    rows.sort(key=lambda r: (r["dep"], r["audio_id"]))
    for r in rows:
        r["model"], r["tier"], r["cost_per_h"] = args.model, args.tier, args.cost_per_h

    out = Path(args.out) if args.out else Path(__file__).parent.parent / "output" / \
        "asr_bench" / f"asr_{args.model}_{args.tier}_{args.context}.csv"
    _write_csv(out, rows)

    _print_summary(rows, deps, args, t0, out)


def _write_csv(out: Path, rows: list[dict]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)


def _print_summary(rows, deps, args, t0, out) -> None:
    # ---- summary (micro-averaged WER = total edits / total ref words) ----
    print(f"\n{'='*64}\n  SUMMARY  model={args.model} tier={args.tier} ctx={args.context}\n{'='*64}")
    ok = [r for r in rows if r["http_status"] == 200]
    print(f"  transcribed: {len(ok)}/{len(rows)}  ({len(rows)-len(ok)} errors)  "
          f"wall={time.perf_counter()-t0:.0f}s")
    for scope in deps + ["ALL"]:
        sub = [r for r in ok if scope == "ALL" or r["dep"] == scope]
        if not sub:
            continue
        tot_edits = sum(r["sub_raw"] + r["del_raw"] + r["ins_raw"] for r in sub)
        tot_words = sum(r["n_ref"] for r in sub)
        micro = tot_edits / tot_words if tot_words else 0.0
        macro = sum(r["wer_raw"] for r in sub) / len(sub)
        durs = [r["duration_s"] for r in sub if isinstance(r["duration_s"], (int, float))]
        p50 = sorted(durs)[len(durs)//2] if durs else 0
        # entity recovery: cs over all rows, sid only over rows that have a SID
        cs_pct = sum(1 for r in sub if r["cs_correct"] is True) / len(sub)
        sid_rows = [r for r in sub if r["sid_canonical"]]
        sid_pct = (sum(1 for r in sid_rows if r["sid_correct"] is True) / len(sid_rows)
                   if sid_rows else 0.0)
        print(f"  {scope.upper():4} n={len(sub):3}  WERraw micro={micro:.1%} macro={macro:.1%}"
              f"  S/D/I={sum(r['sub_raw'] for r in sub)}/{sum(r['del_raw'] for r in sub)}/"
              f"{sum(r['ins_raw'] for r in sub)}  server_p50={p50:.1f}s"
              f"  cs_ok={cs_pct:.0%}  sid_ok={sid_pct:.0%} (n={len(sid_rows)})")
    print(f"\n  CSV: {out}")


def _run_dry(args, deps, audio_root, corpus_by_dep, session_by_dep):
    """Build session lists + new columns offline; write a temp CSV. No service."""
    print(f"{'='*64}\n  DRY-RUN  model={args.model} tier={args.tier} "
          f"ctx={args.context}\n{'='*64}")
    for dep in deps:
        cs_csv, sid_csv = session_by_dep.get(dep, ("", ""))
        cs_list = cs_csv.split(",") if cs_csv else []
        sid_list = sid_csv.split(",") if sid_csv else []
        print(f"\n  [{dep.upper()}] session_callsigns ({len(cs_list)}): "
              f"{', '.join(cs_list)}")
        print(f"  [{dep.upper()}] session_sids ({len(sid_list)}): "
              f"{', '.join(sid_list)}")

    rows = []
    per_dep = 3
    for dep in deps:
        corpus = corpus_by_dep.get(dep)
        if not corpus:
            continue
        wavs = sorted((audio_root / dep).glob("*.wav"))[:per_dep]
        for wav in wavs:
            ent = corpus.get(wav.stem)
            if not ent:
                continue
            rows.append(run_one("", dep, wav, ent["ref"], args.context,
                                args.cost_per_h, dry_run=True))
    for r in rows:
        r["model"], r["tier"], r["cost_per_h"] = args.model, args.tier, args.cost_per_h

    if args.out:
        out = Path(args.out)
    else:
        out = Path(tempfile.gettempdir()) / "asr_bench_dryrun" / \
            f"asr_{args.model}_{args.tier}_{args.context}_dryrun.csv"
    if rows:
        _write_csv(out, rows)

    print(f"\n  {len(rows)} dry-run rows (hyp=ref). Sample entity columns:")
    for r in rows:
        print(f"   {r['audio_id']}: cs={r['cs_canonical'] or '-':10} "
              f"sid={r['sid_canonical'] or '-':9} "
              f"wer_post={r['wer_post']}  ref_norm={r['ref_normalized'][:70]}")
    print(f"\n  CSV: {out}")


if __name__ == "__main__":
    main()
