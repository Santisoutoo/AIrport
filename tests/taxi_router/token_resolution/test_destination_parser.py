from shared.services.taxi_router.destination_parser import extract_destination


def test_runway_simple():
    assert extract_destination("taxi to runway 17 via Tango") == "17"


def test_runway_with_suffix():
    assert extract_destination("taxi to runway 06R via Bravo, Delta") == "06R"
    assert extract_destination("taxi to runway 24L") == "24L"
    assert extract_destination("taxi to runway 09C") == "09C"


def test_holding_point_runway():
    assert extract_destination("taxi to holding point runway 24L") == "24L"
    assert extract_destination("taxi to the holding point of runway 06R via B") == "06R"


def test_holding_short_runway():
    assert extract_destination("holding short of runway 17 via T") == "17"
    assert extract_destination("holding short runway 06R") == "06R"


def test_stand_gate_ramp():
    assert extract_destination("taxi to stand G12 via C") == "G12"
    assert extract_destination("taxi to gate 4 via B") == "4"
    assert extract_destination("taxi to ramp 175 via D") == "175"


def test_holding_point_named_node():
    assert extract_destination("taxi to holding point G1 via C") == "G1"


def test_via_only_returns_none():
    assert extract_destination("taxi via Tango") is None
    assert extract_destination("taxi via Bravo Delta Echo") is None


def test_pushback_only_returns_none():
    assert extract_destination("pushback approved face north") is None


def test_case_insensitive():
    assert extract_destination("TAXI TO RUNWAY 17 VIA TANGO") == "17"
    assert extract_destination("Taxi To Stand G12") == "G12"


def test_empty_and_none():
    assert extract_destination(None) is None
    assert extract_destination("") is None
    assert extract_destination("   ") is None


def test_priority_holding_short_over_runway():
    # "holding short runway 17" must NOT match the generic "runway 17" first
    assert extract_destination("holding short of runway 17") == "17"


def test_priority_holding_point_runway_over_runway():
    assert extract_destination("taxi to holding point runway 06R") == "06R"
