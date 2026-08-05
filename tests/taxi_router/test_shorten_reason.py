"""Unit tests for the pilot-facing rejection phrases (issue #70).

_shorten_reason maps graph-layer error strings — including the strict
routing errors introduced by issue #67 — to the short phrase the simulated
pilot speaks on `hmi:chat` ("<callsign>, unable, <reason>. Request
alternative.").
"""

from shared.services.taxi_router.router import _shorten_reason


# ---- Strict-routing failures (issue #70) ------------------------------------


def test_unknown_taxiway_names_the_token():
    got = _shorten_reason("unknown taxiway 'ZZ99'", [], [])
    assert got == "taxiway ZZ99 not available"


def test_sequence_not_connected_names_the_pair():
    got = _shorten_reason("taxiway sequence not connected: B -> D", [], [])
    assert got == "taxiways B and D are not connected"


def test_no_path_to_first_taxiway():
    got = _shorten_reason("no path from start to taxiway 'Q'", [], [])
    assert got == "unable to reach taxiway Q"


def test_destination_too_far_off_sequence():
    got = _shorten_reason(
        "destination too far from taxiway 'E' (1526m off the authorized sequence)",
        [],
        [],
    )
    assert got == "the issued route does not reach the destination"


def test_destination_not_reachable_along_taxiway():
    got = _shorten_reason("destination not reachable along taxiway 'J'", [], [])
    assert got == "the issued route does not reach the destination"


# ---- Legacy lenient-routing failures ---------------------------------------


def test_via_point_with_token():
    got = _shorten_reason("Could not resolve via point: 'Z'", ["Z"], [])
    assert got == "taxiway Z not found"


def test_generic_no_path():
    got = _shorten_reason("No path from node '1' to node '2'", [], [])
    assert got == "no route available"


def test_off_movement_area():
    got = _shorten_reason(
        "No connected node within 2000m of (0.000000, 0.000000)",
        [],
        [],
    )
    assert got == "position off the movement area"


def test_unknown_error_falls_back():
    assert _shorten_reason("weird internal error", [], []) == "unable to comply"
