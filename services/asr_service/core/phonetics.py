import re

PHONETIC_MAP: dict[str, str] = {
    "alpha": "A",
    "alfa": "A",
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
    "x-ray": "X",
    "xray": "X",
    "yankee": "Y",
    "zulu": "Z",
}

_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in PHONETIC_MAP) + r")\b",
    re.IGNORECASE,
)


def normalize_phonetic(text: str) -> str:
    """Replace isolated ICAO phonetic words with their letter (fallback only)."""
    return _PATTERN.sub(lambda m: PHONETIC_MAP[m.group(0).lower()], text)
