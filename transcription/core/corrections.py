import re

# (pattern, replacement) — order matters: more specific first
_CALLSIGN_FIXES: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\b(bowling|fueling|fooling|dueling|pulling|flying|vomiting|boilong|vuelin)\b', re.IGNORECASE), "Vueling"),
    (re.compile(r'\b(speed\s*burd|speed\s*heard|speedboard)\b', re.IGNORECASE), "Speedbird"),
    (re.compile(r'\b(wizz\s*air|wiz\s*air|whizzair|whizz\s*air)\b', re.IGNORECASE), "Wizzair"),
    (re.compile(r'\b(easy[\s\-]jet)\b', re.IGNORECASE), "EasyJet"),
    (re.compile(r'\b(ryan[\s\-]air|ryan\s*heir)\b', re.IGNORECASE), "Ryanair"),
    (re.compile(r'\b(violeta|bolotea|volote|volta|bolota)\b', re.IGNORECASE), "Volotea"),
    (re.compile(r'\b(helvetica|helvetis|helvetick)\b', re.IGNORECASE), "Helvetic"),
    (re.compile(r'\bair\s*europa\b', re.IGNORECASE), "Air Europa"),
]


def correct_callsigns(text: str) -> str:
    for pattern, replacement in _CALLSIGN_FIXES:
        text = pattern.sub(replacement, text)
    return text
