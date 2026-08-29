"""Aircraft registration generation, shared by both flight plan generators.

Both the fully local generator and the API-backed one need the same rule:
a country/airline prefix plus three random uppercase letters.
"""

import random
import string


def generate_registration(prefix: str = "EC") -> str:
    """Generate a random aircraft registration with the given prefix.

    The prefix may already carry its separator (e.g. ``"N-"``); when it does
    not, a hyphen is inserted, so both ``"EC"`` and ``"EC-"`` yield
    ``"EC-XYZ"``.
    """
    letters = "".join(random.choices(string.ascii_uppercase, k=3))
    if prefix.endswith("-"):
        return f"{prefix}{letters}"
    return f"{prefix}-{letters}"
