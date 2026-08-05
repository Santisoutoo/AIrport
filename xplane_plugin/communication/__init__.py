import re

from XPPython3 import xp


_AIRLINE_NAMES = {
    "RYR": "Ryanair",
    "VLG": "Vueling",
    "BAW": "Speedbird",
    "IBE": "Iberia",
    "AEA": "Europa",
    "AFR": "Airfrance",
    "KLM": "KLM",
    "DLH": "Lufthansa",
    "SWR": "Swiss",
    "AUA": "Austrian",
    "EZY": "Easy",
    "EZS": "Topswiss",
    "WZZ": "Wizzair",
    "TAP": "Air Portugal",
    "ITY": "Itarrow",
    "AAL": "American",
    "DAL": "Delta",
    "UAL": "United",
    "ACA": "Air Canada",
    "EIN": "Shamrock",
    "VIR": "Virgin",
    "SAS": "Scandinavian",
    "FIN": "Finnair",
    "TRA": "Transavia",
    "JAF": "Beauty",
    "TFL": "Orange",
    "QTR": "Qatari",
    "UAE": "Emirates",
    "ETD": "Etihad",
    "THY": "Turkish",
    "ELY": "El Al",
    "DLA": "Dolomiti",
}

_NATO = {
    "A": "Alpha",
    "B": "Bravo",
    "C": "Charlie",
    "D": "Delta",
    "E": "Echo",
    "F": "Foxtrot",
    "G": "Golf",
    "H": "Hotel",
    "I": "India",
    "J": "Juliet",
    "K": "Kilo",
    "L": "Lima",
    "M": "Mike",
    "N": "November",
    "O": "Oscar",
    "P": "Papa",
    "Q": "Quebec",
    "R": "Romeo",
    "S": "Sierra",
    "T": "Tango",
    "U": "Uniform",
    "V": "Victor",
    "W": "Whiskey",
    "X": "X-ray",
    "Y": "Yankee",
    "Z": "Zulu",
}

_DIGITS = {
    "0": "zero",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
}

_CALLSIGN_RE = re.compile(r"\b([A-Z]{3})\s*(\d{1,4}[A-Z]?)\b")

_SPELL_RE = re.compile(
    r"\b(?:"
    r"[A-Z\d]+(?:-[A-Z\d]+)+"  # hyphenated: EI-XZZ
    r"|[A-Z]+\d[A-Z\d]*"  # letter then digit: B12, FL120
    r"|\d+[A-Z][A-Z\d]*"  # digit then letter: 28R, 10L
    r"|\d{2,}(?:\.\d+)?"  # pure digits / freq: 270, 118.5
    r")\b"
)


def _spell_token(token: str) -> str:
    parts = []
    for ch in token:
        if ch.isalpha():
            parts.append(_NATO.get(ch.upper(), ch))
        elif ch.isdigit():
            parts.append(_DIGITS[ch])
        elif ch == ".":
            parts.append("decimal")
        elif ch == "-":
            continue
        else:
            parts.append(ch)
    return " ".join(parts)


def _expand_callsigns(text: str) -> str:
    def _repl(m: re.Match) -> str:
        airline = _AIRLINE_NAMES.get(m.group(1))
        if airline is None:
            return m.group(0)
        return f"{airline} {m.group(2)}"

    return _CALLSIGN_RE.sub(_repl, text)


def _spell_identifiers(text: str) -> str:
    return _SPELL_RE.sub(lambda m: _spell_token(m.group(0)), text)


def speak(text: str) -> None:
    xp.speakString(_spell_identifiers(_expand_callsigns(text)))
