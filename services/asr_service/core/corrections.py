import re

# (pattern, replacement) — order matters: more specific first
_CALLSIGN_FIXES: list[tuple[re.Pattern, str]] = [
    # Vueling
    (
        re.compile(r"\b(bowling|fueling|fooling|dueling|pulling|flying|vomiting|boilong|vuelin)\b", re.IGNORECASE),
        "Vueling",
    ),
    # Speedbird
    (re.compile(r"\b(speed\s*burd|speed\s*heard|speedboard)\b", re.IGNORECASE), "Speedbird"),
    # Wizzair
    (re.compile(r"\b(wizz\s*air|wiz\s*air|whizzair|whizz\s*air)\b", re.IGNORECASE), "Wizzair"),
    # EasyJet
    (re.compile(r"\b(easy[\s\-]jet)\b", re.IGNORECASE), "EasyJet"),
    # Ryanair
    (re.compile(r"\b(ryan[\s\-]air|ryan\s*heir)\b", re.IGNORECASE), "Ryanair"),
    # Volotea
    (re.compile(r"\b(violeta|bolotea|volote|volta|bolota)\b", re.IGNORECASE), "Volotea"),
    # Helvetic
    (re.compile(r"\b(helvetica|helvetis|helvetick)\b", re.IGNORECASE), "Helvetic"),
    # Air Europa — normalise casing
    (re.compile(r"\bair\s*europa\b", re.IGNORECASE), "Air Europa"),
    # Iberia
    (re.compile(r"\b(iberia|iveria|hiberia)\b", re.IGNORECASE), "Iberia"),
    # Iberia Express
    (re.compile(r"\b(iberia\s*express|iberia\s*expres|iberexpres)\b", re.IGNORECASE), "Iberexpres"),
    # Air Nostrum
    (re.compile(r"\b(air\s*nostrum|air\s*nostrom|airnostrum)\b", re.IGNORECASE), "Air Nostrum"),
]


def correct_callsigns(text: str) -> str:
    for pattern, replacement in _CALLSIGN_FIXES:
        text = pattern.sub(replacement, text)
    return text
