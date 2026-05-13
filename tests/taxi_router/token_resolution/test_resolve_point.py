"""Tests for AirportGraph.resolve_point (memoria 5.3.2).

Validates resolution of controller-spoken tokens (runway designator,
taxiway letter, stand id, node name) to (node_id, lat, lon) tuples, plus
priority order and hint-based disambiguation. Most tests are parametrised
across LEST and LEIB (different sizes, different runway counts) using the
`airport` fixture defined in conftest.py.
"""
import pytest


# ---- Runway resolution (via the index, not via resolve_point step 0) -------
#
# In LEST and LEIB the parser assigns sequential numeric node_ids, which means
# numeric runway tokens like "17"/"35" or "06L"/"24R" may collide with
# resolve_point step 0 (direct node_id bypass, graph.py:302). The runway
# threshold lookup itself is exercised via find_nearest_node.

def test_runway_thresholds_have_nearby_nodes(airport):
    for rwy_id in airport.expected_runway_ids:
        ref_lat, ref_lon = airport.graph._runways_by_id[rwy_id]
        node_id, dist = airport.graph.find_nearest_node(
            ref_lat, ref_lon, max_distance=2000.0, restrict_to_main_cc=True,
        )
        assert node_id is not None, (
            f"[{airport.icao}] runway {rwy_id} threshold has no nearby node"
        )
        assert dist < 1000.0, (
            f"[{airport.icao}] runway {rwy_id} threshold {dist:.0f}m away"
        )


# ---- Taxiway resolution (parametrised) -------------------------------------

def test_resolve_taxiway_designators(airport):
    # Pick one or two designators known to exist for each airport.
    for tw in list(airport.expected_taxiway_subset)[:3]:
        if tw in airport.graph.graph.nodes:
            # If the taxiway designator clashes with a node_id, step 0 wins.
            continue
        result = airport.graph.resolve_point(tw)
        assert result is not None, f"[{airport.icao}] failed to resolve {tw!r}"
        assert result[0] in airport.graph._nodes_by_taxiway[tw]


def test_resolve_taxiway_case_insensitive(airport):
    # Choose a taxiway designator that is not also a node_id
    tw = next(
        (t for t in airport.expected_taxiway_subset
         if t not in airport.graph.graph.nodes and t.lower() not in airport.graph.graph.nodes),
        None,
    )
    if tw is None:
        pytest.skip(f"[{airport.icao}] no non-clashing taxiway available")
    lower = airport.graph.resolve_point(tw.lower())
    upper = airport.graph.resolve_point(tw.upper())
    assert lower is not None and upper is not None
    assert lower[0] == upper[0]


# ---- Stand resolution (parametrised) ---------------------------------------

def test_resolve_stand_substring(airport):
    needle = airport.non_numeric_stand_substr
    target = next(
        s for s in airport.raw_data["stands"]
        if needle in str(s.get("stand_id", ""))
    )
    result = airport.graph.resolve_point(needle)
    assert result is not None, f"[{airport.icao}] failed to resolve {needle!r}"
    _, lat, lon = result
    d = airport.graph._calculate_distance(
        lat, lon, target["latitude"], target["longitude"]
    )
    assert d < 1000.0, (
        f"[{airport.icao}] stand {needle!r} snapped {d:.0f}m from target"
    )


# ---- Negative / edge cases (parametrised) ----------------------------------

def test_resolve_unknown_returns_none(airport):
    assert airport.graph.resolve_point("ZZ999_NOT_A_TOKEN") is None


def test_resolve_empty_and_none(airport):
    assert airport.graph.resolve_point(None) is None
    assert airport.graph.resolve_point("") is None
    assert airport.graph.resolve_point("   ") is None


# ---- Direct node_id bypass (parametrised) ----------------------------------

def test_direct_node_id_bypass(airport):
    # Step 0 of resolve_point returns immediately for any token that is a
    # valid node_id. We use node_id "0" which exists in both graphs.
    assert "0" in airport.graph.graph.nodes
    result = airport.graph.resolve_point("0")
    assert result is not None
    node_id, lat, lon = result
    assert node_id == "0"
    n0 = airport.graph.graph.nodes["0"]
    assert lat == n0["lat"] and lon == n0["lon"]


def test_priority_node_id_direct_takes_precedence(airport):
    # The documented order (runway → taxiway → stand → name, graph.py:283-342)
    # is preceded by an undocumented step 0 that captures bare node_ids first.
    # We verify this only when an expected runway designator happens to also
    # be a node_id, which is the situation that creates the collision.
    clashing = [
        r for r in airport.expected_runway_ids if r in airport.graph.graph.nodes
    ]
    if not clashing:
        pytest.skip(
            f"[{airport.icao}] no runway designator collides with a node_id"
        )
    rwy = clashing[0]
    result = airport.graph.resolve_point(rwy)
    assert result is not None
    assert result[0] == rwy  # step 0 wins, returns the bare node_id


# ---- Hint-based disambiguation (LEST-only: LEIB has no useful repeats) ----

def test_resolve_hint_disambiguates_named_nodes(airport):
    if airport.sample_repeated_name is None:
        pytest.skip(
            f"[{airport.icao}] no repeated node name available for disambiguation"
        )
    name = airport.sample_repeated_name
    candidates = [
        n["node_id"] for n in airport.raw_data["nodes"]
        if str(n.get("name", "")).lower() == name.lower()
    ]
    assert len(candidates) >= 2, (
        f"[{airport.icao}] expected ≥2 nodes named {name!r}"
    )

    # Take the two extreme candidates by latitude
    nodes_by_id = {str(n["node_id"]): n for n in airport.raw_data["nodes"]}
    sorted_cands = sorted(
        candidates, key=lambda nid: nodes_by_id[str(nid)]["lat"]
    )
    south_id = str(sorted_cands[0])
    north_id = str(sorted_cands[-1])
    south = nodes_by_id[south_id]
    north = nodes_by_id[north_id]

    near_south = airport.graph.resolve_point(
        name, hint_lat=south["lat"], hint_lon=south["lon"]
    )
    near_north = airport.graph.resolve_point(
        name, hint_lat=north["lat"], hint_lon=north["lon"]
    )
    assert near_south is not None and near_north is not None
    assert near_south[0] == south_id
    assert near_north[0] == north_id


# ---- Named-node resolution (LEST-only: LEIB names are all "node_both") ----

def test_resolve_named_node_exact(lest_graph):
    result = lest_graph.resolve_point("D3_stop")
    assert result is not None
    node_id, _, _ = result
    name = lest_graph.graph.nodes[node_id].get("name", "").lower()
    assert name == "d3_stop"


def test_resolve_named_node_case_insensitive(lest_graph):
    a = lest_graph.resolve_point("D3_stop")
    b = lest_graph.resolve_point("d3_stop")
    assert a is not None and b is not None
    assert a[0] == b[0]
