from shared.models.phases import AIRBORNE_PHASES, ARRIVAL_PHASES, Phase


def test_phase_values_lowercase():
    # Values must stay lowercase to match the strings the AircraftMover emits.
    for p in Phase:
        assert p.value == p.value.lower()


def test_arrival_phases_subset():
    assert Phase.APPROACH.value in ARRIVAL_PHASES
    assert Phase.LANDING_ROLL.value in ARRIVAL_PHASES
    assert Phase.VACATING.value in ARRIVAL_PHASES
    assert Phase.TAXI_IN.value in ARRIVAL_PHASES
    # Departure phases must NOT be marked as arrivals.
    assert Phase.PUSHBACK.value not in ARRIVAL_PHASES
    assert Phase.TAXI_OUT.value not in ARRIVAL_PHASES


def test_airborne_phases():
    assert Phase.APPROACH.value in AIRBORNE_PHASES
    assert Phase.SHORT_FINAL.value in AIRBORNE_PHASES
    assert Phase.AIRBORNE.value in AIRBORNE_PHASES
    assert Phase.PARKED.value not in AIRBORNE_PHASES
    assert Phase.LANDING_ROLL.value not in AIRBORNE_PHASES
