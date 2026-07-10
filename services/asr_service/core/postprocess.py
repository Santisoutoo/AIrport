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
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "niner": 9,
}
DIGIT_WORDS_RE = r"(?:zero|one|two|three|four|five|six|seven|eight|nine|niner)"

PHONETIC_LETTER: dict[str, str] = {
    "alpha": "A", "bravo": "B", "charlie": "C", "delta": "D", "echo": "E",
    "foxtrot": "F", "golf": "G", "hotel": "H", "india": "I", "juliet": "J",
    "kilo": "K", "lima": "L", "mike": "M", "november": "N", "oscar": "O",
    "papa": "P", "quebec": "Q", "romeo": "R", "sierra": "S", "tango": "T",
    "uniform": "U", "victor": "V", "whiskey": "W", "xray": "X", "yankee": "Y",
    "zulu": "Z",
}
LETTER_WORDS_RE = (
    r"(?:alpha|bravo|charlie|delta|echo|foxtrot|golf|hotel|india|juliet|kilo|"
    r"lima|mike|november|oscar|papa|quebec|romeo|sierra|tango|uniform|victor|"
    r"whiskey|xray|yankee|zulu)"
)

RUNWAY_SIDE: dict[str, str] = {"left": "L", "right": "R", "center": "C", "centre": "C"}

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


_SQUAWK_RE = re.compile(
    rf"\bsquawk\s+((?:{DIGIT_WORDS_RE}\s+){{3}}{DIGIT_WORDS_RE})\b", re.IGNORECASE)
_QNH_RE = re.compile(
    rf"\bQNH\s+((?:{DIGIT_WORDS_RE}\s+){{3}}{DIGIT_WORDS_RE})\b", re.IGNORECASE)
_RUNWAY_RE = re.compile(
    rf"\brunway\s+({DIGIT_WORDS_RE})\s+({DIGIT_WORDS_RE})(?:\s+(left|right|center|centre))?\b",
    re.IGNORECASE,
)
_THOUSAND_RE = re.compile(
    rf"\b(initial\s+climb|climb|altitude)\s+"
    rf"((?:{DIGIT_WORDS_RE}\s+)*{DIGIT_WORDS_RE})\s+thousand\b",
    re.IGNORECASE,
)
_FLIGHT_LEVEL_RE = re.compile(
    rf"\bflight level\s+((?:{DIGIT_WORDS_RE}\s+){{2}}{DIGIT_WORDS_RE})\b", re.IGNORECASE)


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

    text = _SQUAWK_RE.sub(_squawk_sub, text)
    text = _QNH_RE.sub(_qnh_sub, text)
    text = _RUNWAY_RE.sub(_runway_sub, text)
    text = _THOUSAND_RE.sub(_thousand_sub, text)
    text = _FLIGHT_LEVEL_RE.sub(_fl_sub, text)
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


def _find_callsign_span(
    tokens: list[tuple[str, int, int]], at_end: bool,
) -> tuple[int, int, str, str] | None:
    """Find "<airline word(s)> <phonetic code>" at the start or end of the token list.

    ATC phraseology always puts the airline name before the phonetic code
    ("Vueling three two alpha ..." / "..., Ryanair four seven three."), so
    both the start and the end case look for the same airline-then-code
    order, just anchored at a different edge of the sentence.
    """
    n = len(tokens)
    if n < 3:
        return None

    for airline_len in (2, 1):
        if not at_end:
            if airline_len >= n:
                continue
            airline_words = [t[0] for t in tokens[:airline_len]]
            if any(_is_phonetic_word(w) for w in airline_words):
                continue
            k = airline_len
            while k < n and (k - airline_len) < 5 and _is_phonetic_word(tokens[k][0]):
                k += 1
            if (k - airline_len) >= 2:
                code = _phonetic_code([t[0] for t in tokens[airline_len:k]])
                if code:
                    return tokens[0][1], tokens[k - 1][2], " ".join(airline_words), code
        else:
            airline_start = n - airline_len
            if airline_start <= 0:
                continue
            airline_words = [t[0] for t in tokens[airline_start:n]]
            if any(_is_phonetic_word(w) for w in airline_words):
                continue
            k = airline_start
            code_len = 0
            while k > 0 and code_len < 5 and _is_phonetic_word(tokens[k - 1][0]):
                k -= 1
                code_len += 1
            if code_len >= 2:
                code = _phonetic_code([t[0] for t in tokens[k:airline_start]])
                if code:
                    return tokens[k][1], tokens[n - 1][2], " ".join(airline_words), code
    return None


def _apply_callsign_fuzzy(text: str, session_callsigns: list[str]) -> tuple[str, str | None, float]:
    if not session_callsigns:
        return text, None, 0.0

    tokens = _alpha_tokens(text)
    hits: list[tuple[float, int, int, str, str]] = []
    for at_end in (False, True):
        found = _find_callsign_span(tokens, at_end)
        if not found:
            continue
        start, end, airline, code = found
        candidate = f"{airline} {code}"
        target, score = _best_fuzzy_match(candidate, session_callsigns)
        if target:
            hits.append((score, start, end, candidate, target))

    if not hits:
        return text, None, 0.0

    hits.sort(key=lambda h: h[0], reverse=True)
    best_score, start, end, candidate, target = hits[0]
    if best_score >= FUZZY_THRESHOLD:
        text = text[:start] + target + text[end:]
    return text, candidate, best_score


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
    if not session_sids:
        return text, None, 0.0

    m = _SID_PHRASE_RE.search(text)
    if m:
        candidate = _sid_candidate_from_phrase(m)
        target, score = _best_fuzzy_match(candidate, session_sids)
        if target and score >= FUZZY_THRESHOLD:
            text = text[:m.start(1)] + target + text[m.end(3):]
        return text, candidate, score

    m = _SID_TOKEN_RE.search(text)
    if m:
        candidate = m.group(0).upper()
        target, score = _best_fuzzy_match(candidate, session_sids)
        if target and score >= FUZZY_THRESHOLD:
            text = text[:m.start()] + target + text[m.end():]
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
    cs_fuzzy_candidate, cs_fuzzy_score, sid_fuzzy_candidate, sid_fuzzy_score.
    """
    session_callsigns = session_callsigns or []
    session_sids = session_sids or []

    after_number_norm = normalize_numbers(text)

    corrected = correct_callsigns(after_number_norm)
    after_callsign_fix, cs_candidate, cs_score = _apply_callsign_fuzzy(
        corrected, session_callsigns)

    after_sid_fix, sid_candidate, sid_score = _apply_sid_fuzzy(
        after_callsign_fix, session_sids)

    # Isolated phonetic letters (taxiways/stands) — applied last so it cannot
    # consume the spelled-out letters the SID pattern above still needs.
    final = normalize_phonetic(after_sid_fix)

    return {
        "after_number_norm": after_number_norm,
        "after_callsign_fix": after_callsign_fix,
        "final": final,
        "cs_fuzzy_candidate": cs_candidate,
        "cs_fuzzy_score": cs_score,
        "sid_fuzzy_candidate": sid_candidate,
        "sid_fuzzy_score": sid_score,
    }
