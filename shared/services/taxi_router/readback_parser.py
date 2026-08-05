"""Extract taxiway tokens and pushback direction from an ICAO pilot readback.

The GND pilot agent returns `taxi_data.taxi_route` as a spoken sequence
(e.g. "Bravo, Delta, Echo") and an `instruction_text` that contains the
full readback phrase. We prefer the structured field when present and
fall back to regex over the text when it is not.
"""

import re
from typing import Iterable, Optional

_PHONETIC = {
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
    "juliett": "J",
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
    "x-ray": "X",
    "yankee": "Y",
    "zulu": "Z",
}

_NUMBER_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "niner": "9",
}

_CARDINAL_TO_DEG = {
    "north": 0.0,
    "east": 90.0,
    "south": 180.0,
    "west": 270.0,
    "northeast": 45.0,
    "southeast": 135.0,
    "southwest": 225.0,
    "northwest": 315.0,
}


def _normalise(text: str) -> str:
    """Lowercase, strip punctuation that isn't a digit/letter/space."""
    text = text.lower()
    text = re.sub(r"[.,;:!?()\[\]]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _collapse_phonetic(tokens: list[str]) -> list[str]:
    """Turn sequences like ['golf','one','zero'] into ['G10']; 'bravo' into 'B'."""
    out: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        letter = _PHONETIC.get(t)
        if letter is None:
            out.append(t)
            i += 1
            continue
        # Collect following number words / digits
        digits = ""
        j = i + 1
        while j < len(tokens):
            nxt = tokens[j]
            if nxt in _NUMBER_WORDS:
                digits += _NUMBER_WORDS[nxt]
                j += 1
            elif nxt.isdigit():
                digits += nxt
                j += 1
            else:
                break
        out.append(letter + digits if digits else letter)
        i = j
    return out


def extract_taxiway_tokens(
    taxi_route_text: Optional[str],
    fallback_text: Optional[str] = None,
    known_tokens: Optional[Iterable[str]] = None,
    dedup: bool = True,
) -> list[str]:
    """Return the pilot's taxi sequence as an ordered list of canonical tokens.

    Prefers `taxi_route_text` when non-empty; otherwise scans `fallback_text`.
    When `known_tokens` is provided, tokens not in that set are filtered out.

    With `dedup=True` (default) every repeated token is dropped, keeping the
    historical behaviour. Strict-routing callers (issue #69) pass
    `dedup=False`: only *consecutive* duplicates are collapsed (phonetic
    repetition like "alpha alpha"), so a clearance that legitimately revisits
    a taxiway ("via A, B, A") keeps its full sequence.
    """
    source = taxi_route_text if taxi_route_text and taxi_route_text.strip() else fallback_text
    if not source:
        return []

    normalised = _normalise(source)
    # Split on commas, 'and', whitespace -- we'll re-collapse phonetic runs.
    raw = re.split(r"\s+|,|\band\b", normalised)
    raw = [t for t in raw if t]

    collapsed = _collapse_phonetic(raw)

    known_upper: Optional[set[str]] = None
    if known_tokens is not None:
        known_upper = {str(t).upper() for t in known_tokens}

    out: list[str] = []
    seen: set[str] = set()
    for tok in collapsed:
        t = tok.upper()
        # Skip anything that doesn't look like a taxiway token (letter +/- digits)
        if not re.fullmatch(r"[A-Z][A-Z0-9]*", t):
            continue
        if known_upper is not None and t not in known_upper:
            continue
        if dedup:
            if t in seen:
                continue
            seen.add(t)
        elif out and out[-1] == t:
            # Collapse only consecutive repeats ("alpha alpha" stutter)
            continue
        out.append(t)
    return out


# -- Pushback direction --------------------------------------------------------

_FACE_PATTERNS = [
    # "face north", "facing south-west", "face the east"
    re.compile(r"fac(?:e|ing)\s+(?:the\s+)?([a-z\-]+)"),
    # "face 090", "facing 180 degrees"
    re.compile(r"fac(?:e|ing)\s+(\d{1,3})"),
]


def parse_pushback_direction(text: Optional[str]) -> Optional[float]:
    """Extract the target heading from a pushback clearance.

    Accepts cardinals ("north"/"south-east"), intercardinals, and numeric
    headings ("face 090"). Returns degrees in [0, 360) or None when unknown.
    """
    if not text:
        return None
    t = _normalise(text)
    for pat in _FACE_PATTERNS:
        m = pat.search(t)
        if not m:
            continue
        raw = m.group(1)
        if raw.isdigit():
            deg = float(raw) % 360.0
            return deg
        key = raw.replace("-", "").replace(" ", "")
        if key in _CARDINAL_TO_DEG:
            return _CARDINAL_TO_DEG[key]
    return None
