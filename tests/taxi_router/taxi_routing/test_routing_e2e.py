"""End-to-end taxi-routing tests (memoria 5.3.3).

Validates find_route_via and find_route_from_position over the real LEST and
LEIB graphs. The two airports differ substantially in size (96 vs 188 nodes)
and complexity, which exercises the routing engine on graphs of clearly
different scale.
"""
import math

import networkx as nx
import pytest


# ---- Helpers ---------------------------------------------------------------

def _pick_route_pair(airport):
    """Pick a (start, end) coordinate pair that produces a valid route.

    Iterates over stands and runway designators until find_route_from_position
    succeeds. Needed because some airports (e.g. LEIB) have stands or runway
    threshold nodes split across disconnected components -- we must avoid such
    pairs to test the happy-path routing.
    """
    for s in airport.raw_data["stands"]:
        for end_token in airport.expected_runway_ids:
            r = airport.graph.find_route_from_position(
                s["latitude"], s["longitude"], end_token,
            )
            if r.get("success"):
                return s, end_token
    raise RuntimeError(
        f"[{airport.icao}] no (stand, runway) pair produces a connected route"
    )


# ---- Happy-path routes (parametrised) --------------------------------------

def test_route_from_position_succeeds(airport):
    start, end = _pick_route_pair(airport)
    r = airport.graph.find_route_from_position(
        start["latitude"], start["longitude"], end,
    )
    assert r["success"] is True, (
        f"[{airport.icao}] route from {start['stand_id']!r} to {end!r}: "
        f"{r.get('error')}"
    )
    assert len(r["path_node_ids"]) >= 2
    assert r["total_distance_m"] > 0


def test_trivial_path_start_equals_end(airport):
    # Use the first node_id (always "0") for both endpoints, exploiting
    # resolve_point step 0 to make the test airport-agnostic.
    r = airport.graph.find_route_via("0", "0")
    assert r["success"] is True
    assert len(r["path_node_ids"]) == 1
    assert r["total_distance_m"] == 0.0


# ---- Error paths (parametrised) --------------------------------------------

def test_route_from_position_no_connected_node(airport):
    r = airport.graph.find_route_from_position(0.0, 0.0, "0")
    assert r["success"] is False
    assert "No connected node" in r["error"]


def test_invalid_end_token(airport):
    r = airport.graph.find_route_via("0", "XYZ_NOT_A_TOKEN")
    assert r["success"] is False
    assert "Could not resolve end token" in r["error"]


def test_invalid_start_token(airport):
    rwy = next(iter(airport.expected_runway_ids))
    r = airport.graph.find_route_via("XYZ_NOT_A_TOKEN", rwy)
    assert r["success"] is False
    assert "Could not resolve start token" in r["error"]


# ---- Result shape (parametrised) -------------------------------------------

def test_result_shape_keys(airport):
    start, end = _pick_route_pair(airport)
    r = airport.graph.find_route_from_position(
        start["latitude"], start["longitude"], end,
    )
    assert r["success"], f"[{airport.icao}] precondition failed: {r.get('error')}"
    for key in (
        "success", "path_node_ids", "waypoints",
        "taxiway_sequence", "total_distance_m", "start", "end",
    ):
        assert key in r, f"[{airport.icao}] missing key: {key}"
    for sub in ("node_id", "lat", "lon", "token"):
        assert sub in r["start"]
        assert sub in r["end"]


def test_waypoints_have_valid_coords(airport):
    start, end = _pick_route_pair(airport)
    r = airport.graph.find_route_from_position(
        start["latitude"], start["longitude"], end,
    )
    assert r["success"]
    for wp in r["waypoints"]:
        assert wp["node_id"]
        assert -90 <= wp["lat"] <= 90
        assert -180 <= wp["lon"] <= 180


def test_taxiway_sequence_no_consecutive_duplicates(airport):
    start, end = _pick_route_pair(airport)
    r = airport.graph.find_route_from_position(
        start["latitude"], start["longitude"], end,
    )
    seq = r["taxiway_sequence"]
    for i in range(1, len(seq)):
        assert seq[i] != seq[i - 1], (
            f"[{airport.icao}] consecutive duplicate at index {i}: {seq}"
        )


# ---- Structural invariants (parametrised) ----------------------------------

def test_consecutive_path_nodes_are_connected(airport):
    start, end = _pick_route_pair(airport)
    r = airport.graph.find_route_from_position(
        start["latitude"], start["longitude"], end,
    )
    assert r["success"]
    path = r["path_node_ids"]
    for i in range(len(path) - 1):
        assert airport.graph.graph.has_edge(path[i], path[i + 1]), (
            f"[{airport.icao}] path[{i}]={path[i]} -> "
            f"path[{i+1}]={path[i+1]} is not an edge"
        )


def test_total_distance_matches_edge_sum(airport):
    start, end = _pick_route_pair(airport)
    r = airport.graph.find_route_from_position(
        start["latitude"], start["longitude"], end,
    )
    assert r["success"]
    path = r["path_node_ids"]
    expected = sum(
        airport.graph.graph.edges[path[i], path[i + 1]]["weight"]
        for i in range(len(path) - 1)
    )
    assert math.isclose(r["total_distance_m"], expected, abs_tol=0.1)


def test_astar_matches_dijkstra_distance(airport):
    start, end = _pick_route_pair(airport)
    r = airport.graph.find_route_from_position(
        start["latitude"], start["longitude"], end,
    )
    assert r["success"]
    start_node = r["start"]["node_id"]
    end_node = r["end"]["node_id"]
    dijkstra = nx.shortest_path_length(
        airport.graph.graph, start_node, end_node, weight="weight"
    )
    # find_route_from_position adds the snap distance; we compare the pure
    # graph distance between the resolved endpoints.
    expected = sum(
        airport.graph.graph.edges[r["path_node_ids"][i], r["path_node_ids"][i+1]]["weight"]
        for i in range(len(r["path_node_ids"]) - 1)
    )
    assert math.isclose(expected, dijkstra, abs_tol=0.5)


def test_heuristic_is_admissible(airport):
    # Sweep over stands and runway tokens and check, for the first 3 routes
    # that succeed, that the straight-line Haversine never exceeds the actual
    # graph route length. Stands disconnected from any runway are skipped.
    checked = 0
    for s in airport.raw_data["stands"]:
        for end_token in airport.expected_runway_ids:
            r = airport.graph.find_route_from_position(
                s["latitude"], s["longitude"], end_token,
            )
            if not r.get("success"):
                continue
            straight = airport.graph._calculate_distance(
                r["start"]["lat"], r["start"]["lon"],
                r["end"]["lat"], r["end"]["lon"],
            )
            assert straight <= r["total_distance_m"] + 1e-6, (
                f"[{airport.icao}] heuristic violated admissibility for stand "
                f"{s['stand_id']!r}: straight={straight}, route={r['total_distance_m']}"
            )
            checked += 1
            if checked >= 3:
                return
    assert checked >= 1, f"[{airport.icao}] no admissibility check ran"


# ---- LEST-specific route documenting the via backtracking behaviour --------

def test_route_with_via_passes_through_taxiway_node(lest_graph):
    r = lest_graph.find_route_via("11", "35", via=["E1"])
    assert r["success"] is True
    e1_nodes = set(lest_graph._nodes_by_taxiway["E1"])
    assert any(n in e1_nodes for n in r["path_node_ids"]), (
        f"path did not pass through any E1 node ({sorted(e1_nodes)})"
    )


# ---- Documented behaviour (xfail) ------------------------------------------

@pytest.mark.xfail(
    reason="Best-effort via behaviour: an unknown taxiway in `via` is silently "
    "ignored by _find_nearest_via_start (graph.py). The route succeeds but "
    "does not force the missing waypoint. Documented for memoria 5.3.3 as a "
    "deliberate design decision to be discussed."
)
def test_via_with_unknown_taxiway_raises_or_warns(lest_graph):
    r = lest_graph.find_route_via("11", "35", via=["ZZ99"])
    assert r["success"] is False
    assert "ZZ99" in r.get("error", "")
