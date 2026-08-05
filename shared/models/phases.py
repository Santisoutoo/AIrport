"""Aircraft phase constants.

Values are kept lowercase to match the strings already emitted by
`AircraftMover` and `AircraftStateStore` (e.g. "parked", "pushback",
"taxi_out", "holding"). The HMI maps these to display columns.
"""

from enum import Enum


class Phase(str, Enum):
    # Pre-departure / shared
    PARKED = "parked"
    PUSHBACK = "pushback"
    TAXI_OUT = "taxi_out"
    HOLDING = "holding"

    # Departure flight
    LINEUP = "lineup"
    TAKEOFF_ROLL = "takeoff_roll"
    AIRBORNE = "airborne"

    # Arrival flight
    APPROACH = "approach"
    SHORT_FINAL = "short_final"
    LANDING_ROLL = "landing_roll"
    VACATING = "vacating"
    TAXI_IN = "taxi_in"


ARRIVAL_PHASES = frozenset(
    {
        Phase.APPROACH.value,
        Phase.SHORT_FINAL.value,
        Phase.LANDING_ROLL.value,
        Phase.VACATING.value,
        Phase.TAXI_IN.value,
    }
)

AIRBORNE_PHASES = frozenset(
    {
        Phase.AIRBORNE.value,
        Phase.APPROACH.value,
        Phase.SHORT_FINAL.value,
    }
)
