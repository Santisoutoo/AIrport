"""Postprocessing pipeline for raw Whisper transcriptions.

Ports the phonetic-decoding logic already validated in
agents_evaluation/validate_agents.py (PHONETIC_DIGIT with "niner",
PHONETIC_LETTER, DIGIT_WORDS_RE, runway_code). Copied (not imported) because
the service is containerised with only its own folder.

Pipeline (see postprocess_transcription):
  1. Number normalisation: phonetic digits -> figures, but ONLY inside known
     ATC contexts (squawk, QNH, runway, climb/altitude thousands, flight
     level). Digits outside those contexts are left untouched.
  2. Callsign correction: known-typo fixes (core.corrections) + fuzzy match
     against the active session callsigns, if provided.
  3. SID correction: pattern match ("via [the] <name> <digit> <letter>
     departure" or a bare "<NAME><digit><letter>" token) + fuzzy match
     against the session SIDs, if provided.
  4. Isolated phonetic letters (taxiways, stands, e.g. "via alpha bravo" ->
     "via A B") are normalised last, so they cannot interfere with the SID
     pattern above (which still needs the spelled-out letter word).
"""

import re

from .corrections import correct_callsigns
from .phonetics import normalize_phonetic

# ---------------------------------------------------------------------------
# Phonetic vocabularies (copied from agents_evaluation/validate_agents.py)
# ---------------------------------------------------------------------------

PHONETIC_DIGIT: dict[str, int] = {
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

PHONETIC_LETTER: dict[str, str] = {
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

RUNWAY_SIDE: dict[str, str] = {"left": "L", "right": "R", "center": "C", "centre": "C"}

# Radiotelephony airline name (lowercase) -> ICAO designator. Used to compact
# spoken callsigns into their canonical ICAO form ("Ryanair four seven three"
# -> "RYR473"). Exported so the offline benchmark can reuse the same mapping.
AIRLINE_ICAO: dict[str, str] = {
    "ryanair": "RYR",
    "iberia": "IBE",
    "vueling": "VLG",
    "lufthansa": "DLH",
    "swiss": "SWR",
    "aer lingus": "EIN",
    "wizzair": "WZZ",
    "speedbird": "BAW",
    "easyjet": "EZY",
    "volotea": "VOE",
    "helvetic": "OAW",
    "air europa": "AEA",
    "iberexpres": "IBS",
    "air nostrum": "ANE",
}

# Words that must never be treated as the airline part of a callsign span.
# The span finder can otherwise latch onto a phonetic SID/number tail preceding
# a plain ATC word (e.g. "... one GOLF departure"), which would corrupt the
# text. Real radiotelephony airline names never appear in this set.
_NON_AIRLINE_WORDS: frozenset[str] = frozenset(
    {
        "departure",
        "arrival",
        "approach",
        "ground",
        "tower",
        "delivery",
        "control",
        "radar",
        "information",
        "traffic",
        "apron",
        "runway",
        "squawk",
        "contact",
        "report",
        "readback",
        "correct",
        "cleared",
        "clear",
        "holding",
        "hold",
        "point",
        "taxi",
        "wait",
        "degrees",
        "knots",
        "heading",
        "climb",
        "descend",
        "descent",
        "maintain",
        "expect",
        "ready",
        "wind",
        "feet",
        "thousand",
        "level",
        "flight",
        "left",
        "right",
        "center",
        "centre",
        "north",
        "south",
        "east",
        "west",
        "pushback",
        "push",
        "start",
        "line",
        "when",
        "the",
        "via",
        "and",
        "to",
        "on",
        "for",
        "with",
        "at",
        "of",
    }
)

FUZZY_THRESHOLD = 80.0

# ---------------------------------------------------------------------------
# Fuzzy matching — rapidfuzz preferred, difflib fallback
# ---------------------------------------------------------------------------

try:
    from rapidfuzz import fuzz as _rapidfuzz_fuzz

    def _similarity(a: str, b: str) -> float:
        return _rapidfuzz_fuzz.ratio(a, b)
except ImportError:  # pragma: no cover - exercised only without rapidfuzz installed
    from difflib import SequenceMatcher

    def _similarity(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio() * 100.0


def _best_fuzzy_match(candidate: str, options: list[str]) -> tuple[str | None, float]:
    """Return (best matching option, similarity score 0-100) or (None, 0.0)."""
    if not candidate or not options:
        return None, 0.0
    best_opt, best_score = None, 0.0
    for opt in options:
        score = _similarity(candidate.upper(), opt.upper())
        if score > best_score:
            best_opt, best_score = opt, score
    return best_opt, best_score


# ---------------------------------------------------------------------------
# 1. Number normalisation (context-aware only)
# ---------------------------------------------------------------------------


def _phonetic_words_to_digits(words: list[str]) -> str:
    return "".join(str(PHONETIC_DIGIT[w.lower()]) for w in words)


_SQUAWK_RE = re.compile(rf"\bsquawk\s+((?:{DIGIT_WORDS_RE}\s+){{3}}{DIGIT_WORDS_RE})\b", re.IGNORECASE)
_QNH_RE = re.compile(rf"\bQNH\s+((?:{DIGIT_WORDS_RE}\s+){{3}}{DIGIT_WORDS_RE})\b", re.IGNORECASE)
_RUNWAY_RE = re.compile(
    rf"\brunway\s+({DIGIT_WORDS_RE})\s+({DIGIT_WORDS_RE})(?:\s+(left|right|center|centre))?\b",
    re.IGNORECASE,
)
_THOUSAND_RE = re.compile(
    rf"\b(initial\s+climb|climb|altitude)\s+"
    rf"((?:{DIGIT_WORDS_RE}\s+)*{DIGIT_WORDS_RE})\s+thousand\b",
    re.IGNORECASE,
)
_FLIGHT_LEVEL_RE = re.compile(rf"\bflight level\s+((?:{DIGIT_WORDS_RE}\s+){{2}}{DIGIT_WORDS_RE})\b", re.IGNORECASE)
# Radio frequency: three integer digits, "decimal"/"point", then 1-3 decimals
# ("one two one decimal six five five" -> "121.655").
_FREQ_RE = re.compile(
    rf"\b((?:{DIGIT_WORDS_RE}\s+){{2}}{DIGIT_WORDS_RE})\s+(?:decimal|point)\s+"
    rf"({DIGIT_WORDS_RE}(?:\s+{DIGIT_WORDS_RE}){{0,2}})\b",
    re.IGNORECASE,
)


def normalize_numbers(text: str) -> str:
    """Convert phonetic digit sequences to figures, only inside known ATC contexts."""

    def _squawk_sub(m: re.Match) -> str:
        return "squawk " + _phonetic_words_to_digits(m.group(1).split())

    def _qnh_sub(m: re.Match) -> str:
        return "QNH " + _phonetic_words_to_digits(m.group(1).split())

    def _runway_sub(m: re.Match) -> str:
        digits = _phonetic_words_to_digits([m.group(1), m.group(2)])
        side = RUNWAY_SIDE.get((m.group(3) or "").lower(), "")
        return "runway " + digits + side

    def _thousand_sub(m: re.Match) -> str:
        trigger = m.group(1)
        value = int(_phonetic_words_to_digits(m.group(2).split())) * 1000
        return f"{trigger} {value}"

    def _fl_sub(m: re.Match) -> str:
        return "FL" + _phonetic_words_to_digits(m.group(1).split())

    def _freq_sub(m: re.Match) -> str:
        integer = _phonetic_words_to_digits(m.group(1).split())
        decimals = _phonetic_words_to_digits(m.group(2).split())
        return f"{integer}.{decimals}"

    text = _SQUAWK_RE.sub(_squawk_sub, text)
    text = _QNH_RE.sub(_qnh_sub, text)
    text = _RUNWAY_RE.sub(_runway_sub, text)
    text = _THOUSAND_RE.sub(_thousand_sub, text)
    text = _FLIGHT_LEVEL_RE.sub(_fl_sub, text)
    text = _FREQ_RE.sub(_freq_sub, text)
    return text


# ---------------------------------------------------------------------------
# 2. Callsign fuzzy correction
# ---------------------------------------------------------------------------

_ALPHA_TOKEN_RE = re.compile(r"[A-Za-z]+")


def _alpha_tokens(text: str) -> list[tuple[str, int, int]]:
    """List of (word, start_char, end_char) for every alphabetic token in text."""
    return [(m.group(0), m.start(), m.end()) for m in _ALPHA_TOKEN_RE.finditer(text)]


def _is_phonetic_word(word: str) -> bool:
    wl = word.lower()
    return wl in PHONETIC_DIGIT or wl in PHONETIC_LETTER


def _phonetic_code(words: list[str]) -> str:
    out = []
    for w in words:
        wl = w.lower()
        if wl in PHONETIC_DIGIT:
            out.append(str(PHONETIC_DIGIT[wl]))
        elif wl in PHONETIC_LETTER:
            out.append(PHONETIC_LETTER[wl])
    return "".join(out)


# Airline names are at most two words ("Air Europa"); the longer form is tried
# first so "Air Nostrum" is not truncated to "Nostrum".
_AIRLINE_LENGTHS = (2, 1)
_MIN_CODE_WORDS = 2
_MAX_CODE_WORDS = 5

# A span is (start_char, end_char, airline words, phonetic code).
_Span = tuple[int, int, str, str]


def _airline_words(tokens: list[tuple[str, int, int]], start: int, stop: int) -> list[str] | None:
    """Words of a candidate airline name, or None if any of them is phonetic."""
    words = [t[0] for t in tokens[start:stop]]
    if any(_is_phonetic_word(w) for w in words):
        return None
    return words


def _span_at_start(tokens: list[tuple[str, int, int]], airline_len: int) -> _Span | None:
    """Match "<airline> <phonetic code>" anchored at the first token."""
    n = len(tokens)
    if airline_len >= n:
        return None

    words = _airline_words(tokens, 0, airline_len)
    if words is None:
        return None

    # Consume the phonetic code that follows the airline name.
    k = airline_len
    while k < n and (k - airline_len) < _MAX_CODE_WORDS and _is_phonetic_word(tokens[k][0]):
        k += 1
    if (k - airline_len) < _MIN_CODE_WORDS:
        return None

    code = _phonetic_code([t[0] for t in tokens[airline_len:k]])
    if not code:
        return None
    return tokens[0][1], tokens[k - 1][2], " ".join(words), code


def _span_at_end(tokens: list[tuple[str, int, int]], airline_len: int) -> _Span | None:
    """Match "<phonetic code> <airline>" anchored at the last token."""
    n = len(tokens)
    airline_start = n - airline_len
    if airline_start <= 0:
        return None

    words = _airline_words(tokens, airline_start, n)
    if words is None:
        return None

    # Walk backwards from the airline name over the phonetic code.
    k = airline_start
    code_len = 0
    while k > 0 and code_len < _MAX_CODE_WORDS and _is_phonetic_word(tokens[k - 1][0]):
        k -= 1
        code_len += 1
    if code_len < _MIN_CODE_WORDS:
        return None

    code = _phonetic_code([t[0] for t in tokens[k:airline_start]])
    if not code:
        return None
    return tokens[k][1], tokens[n - 1][2], " ".join(words), code


def _find_callsign_span(tokens: list[tuple[str, int, int]], at_end: bool) -> _Span | None:
    """Find an "<airline> <phonetic code>" pair at one edge of the token list.

    With ``at_end=False`` the airline name must be the first token(s), followed
    by the code ("Vueling three two alpha ..."). With ``at_end=True`` the
    airline name must be the *last* token(s), preceded by the code. Callers
    filter the result through ``_NON_AIRLINE_WORDS`` because the trailing form
    also matches plain ATC tails ("... one golf departure").
    """
    if len(tokens) < 3:
        return None

    scan = _span_at_end if at_end else _span_at_start
    for airline_len in _AIRLINE_LENGTHS:
        span = scan(tokens, airline_len)
        if span is not None:
            return span
    return None


def _compact_callsign(airline: str, code: str) -> tuple[str, bool]:
    """Return (compacted callsign, airline_known).

    Known airline -> "<ICAO designator><code>" ("RYR473"). Unknown airline ->
    the name kept verbatim with the compacted code ("Fictional 47B"); we never
    invent a designator.
    """
    designator = AIRLINE_ICAO.get(airline.lower())
    if designator:
        return f"{designator}{code}", True
    return f"{airline} {code}", False


def _apply_callsign_compaction(
    text: str,
    session_callsigns: list[str],
) -> tuple[str, str | None, float, bool]:
    """Compact every callsign span into ICAO form and optionally snap to session.

    For each span found (start and/or end of the sentence):
      * build the ICAO form via AIRLINE_ICAO,
      * if session callsigns are given and the fuzzy score over the ICAO form
        is >= FUZZY_THRESHOLD, replace with the canonical session callsign,
      * otherwise leave the compacted ICAO form,
      * unknown airlines keep their spoken name (flagged) and are never given a
        made-up designator.

    Returns (text, cs_icao, cs_fuzzy_score, cs_unknown_airline) for the primary
    (most confidently resolved) span, or (text, None, 0.0, False) if none.
    """
    session_callsigns = session_callsigns or []
    tokens = _alpha_tokens(text)

    spans: list[tuple[int, int, str, str]] = []
    seen: set[tuple[int, int]] = set()
    for at_end in (False, True):
        found = _find_callsign_span(tokens, at_end)
        if not found:
            continue
        start, end, airline, code = found
        if any(w.lower() in _NON_AIRLINE_WORDS for w in airline.split()):
            continue  # phonetic SID/number tail masquerading as a callsign
        key = (start, end)
        if key in seen:
            continue
        seen.add(key)
        spans.append(found)

    if not spans:
        return text, None, 0.0, False

    # (start, end, replacement, icao_form, known, score, resolved)
    reps: list[tuple[int, int, str, str, bool, float, bool]] = []
    for start, end, airline, code in spans:
        icao_form, known = _compact_callsign(airline, code)
        replacement, score, resolved = icao_form, 0.0, False
        if session_callsigns:
            target, score = _best_fuzzy_match(icao_form, session_callsigns)
            if target and score >= FUZZY_THRESHOLD:
                replacement, resolved = target, True
        reps.append((start, end, replacement, icao_form, known, score, resolved))

    # Apply right-to-left so earlier char offsets stay valid.
    for start, end, replacement, *_ in sorted(reps, key=lambda r: r[0], reverse=True):
        text = text[:start] + replacement + text[end:]

    # Report the most confidently resolved span (resolved > known > score).
    primary = max(reps, key=lambda r: (r[6], r[4], r[5]))
    _, _, _, icao_form, known, score, resolved = primary
    cs_unknown_airline = (not known) and (not resolved)
    return text, icao_form, score, cs_unknown_airline


# ---------------------------------------------------------------------------
# 3. SID fuzzy correction
# ---------------------------------------------------------------------------

_SID_PHRASE_RE = re.compile(
    rf"via\s+(?:the\s+)?([A-Za-z]+)\s+({DIGIT_WORDS_RE})\s+({LETTER_WORDS_RE})\s+departure",
    re.IGNORECASE,
)
_SID_TOKEN_RE = re.compile(r"\b([A-Za-z]{3,6})(\d)([A-Za-z])\b")


def _sid_candidate_from_phrase(m: re.Match) -> str:
    name, digit_word, letter_word = m.group(1), m.group(2), m.group(3)
    return f"{name.upper()}{PHONETIC_DIGIT[digit_word.lower()]}{PHONETIC_LETTER[letter_word.lower()]}"


def _apply_sid_fuzzy(text: str, session_sids: list[str]) -> tuple[str, str | None, float]:
    session_sids = session_sids or []

    m = _SID_PHRASE_RE.search(text)
    if m:
        candidate = _sid_candidate_from_phrase(m)
        # Snap to the session SID if it matches confidently, otherwise compact
        # the spelled-out phrase to the bare token ("via BELEN1G departure").
        chosen, score = candidate, 0.0
        if session_sids:
            target, score = _best_fuzzy_match(candidate, session_sids)
            if target and score >= FUZZY_THRESHOLD:
                chosen = target
        via_word = text[m.start() : m.start() + 3]  # preserve "via"/"Via" casing
        text = f"{text[: m.start()]}{via_word} {chosen} departure{text[m.end() :]}"
        return text, candidate, score

    m = _SID_TOKEN_RE.search(text)
    if m:
        candidate = m.group(0).upper()
        score = 0.0
        if session_sids:
            target, score = _best_fuzzy_match(candidate, session_sids)
            if target and score >= FUZZY_THRESHOLD:
                text = text[: m.start()] + target + text[m.end() :]
        return text, candidate, score

    return text, None, 0.0


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def postprocess_transcription(
    text: str,
    session_callsigns: list[str] | None = None,
    session_sids: list[str] | None = None,
) -> dict:
    """Run the full postprocessing pipeline and return every intermediate step.

    Returns a dict with: after_number_norm, after_callsign_fix, final,
    cs_fuzzy_candidate, cs_fuzzy_score, sid_fuzzy_candidate, sid_fuzzy_score,
    cs_icao, cs_unknown_airline.
    """
    session_callsigns = session_callsigns or []
    session_sids = session_sids or []

    after_number_norm = normalize_numbers(text)

    corrected = correct_callsigns(after_number_norm)
    after_callsign_fix, cs_icao, cs_score, cs_unknown_airline = _apply_callsign_compaction(corrected, session_callsigns)

    after_sid_fix, sid_candidate, sid_score = _apply_sid_fuzzy(after_callsign_fix, session_sids)

    # Isolated phonetic letters (taxiways/stands) — applied last so it cannot
    # consume the spelled-out letters the SID pattern above still needs.
    final = normalize_phonetic(after_sid_fix)

    return {
        "after_number_norm": after_number_norm,
        "after_callsign_fix": after_callsign_fix,
        "final": final,
        "cs_fuzzy_candidate": cs_icao,
        "cs_fuzzy_score": cs_score,
        "sid_fuzzy_candidate": sid_candidate,
        "sid_fuzzy_score": sid_score,
        "cs_icao": cs_icao,
        "cs_unknown_airline": cs_unknown_airline,
    }


def normalize_reference(text: str) -> str:
    """Canonicalise a clean corpus reference the same way as a transcription.

    Applies number/frequency normalisation, ICAO callsign compaction, SID
    compaction and phonetic-letter expansion without needing any session list,
    so a reference and a postprocessed hypothesis can be compared on equal
    footing (WER-post). Returns just the canonicalised string.
    """
    return postprocess_transcription(text)["final"]
