"""Extract a taxi destination token from a controller-issued instruction.

The destination is whatever the controller explicitly said as the endpoint
of the taxi: runway, holding point, stand/gate, or a named node. If the
controller did not say one, we return None and the router falls back to
the last via-point.

Patterns are ordered most-specific → least-specific so that e.g. "holding
short of runway 17" is recognised as runway 17 rather than the generic
"runway" word match.
"""

import re
from typing import Optional

_PATTERNS: list[re.Pattern] = [
    # "holding short (of) runway 17L"
    re.compile(r"\bholding\s+short\s+(?:of\s+)?runway\s+(\d{1,2}[lrc]?)\b"),
    # "to (the) holding point (of) runway 06R"
    re.compile(r"\bto\s+(?:the\s+)?holding\s+point\s+(?:of\s+)?runway\s+(\d{1,2}[lrc]?)\b"),
    # "to (the) runway 24L"
    re.compile(r"\bto\s+(?:the\s+)?runway\s+(\d{1,2}[lrc]?)\b"),
    # "to (the) stand/gate/ramp G12"
    re.compile(r"\bto\s+(?:the\s+)?(?:stand|gate|ramp)\s+([a-z0-9]+)\b"),
    # "to (the) holding point G1"
    re.compile(r"\bto\s+(?:the\s+)?holding\s+point\s+([a-z]\d*)\b"),
]


def extract_destination(text: Optional[str]) -> Optional[str]:
    """Return the endpoint token the controller specified, or None.

    Output is uppercased (what `AirportGraph.resolve_point` expects). We
    only emit the token itself — callers feed it directly into A*.
    """
    if not text:
        return None
    normalised = text.lower()
    for pat in _PATTERNS:
        m = pat.search(normalised)
        if m:
            return m.group(1).upper()
    return None
