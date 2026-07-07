"""Tests for AirportGraph construction (memoria 5.3.1).

Most tests are parametrised over the airport(s) configured in conftest.py
(currently LEBL) so that the structural invariants are verified on a real,
large graph. Airport-specific tests (the xfail documenting the
`find_nearest_node` defect) stay attached to the single `lebl_graph` fixture.
"""
import math

import networkx as nx
import pytest

from plugins.GND.graph import AirportGraph


# ---- Construction entry points ---------------------------------------------

@pytest.mark.parametrize("json_path_fixture", ["lebl_json_path"])
def test_build_from_json_file_path(request, json_path_fixture):
    path = request.getfixturevalue(json_path_fixture)
    g = AirportGraph(path)
    assert g.graph.number_of_nodes() > 0
    assert g.graph.number_of_edges() > 0


def test_build_from_dict_data(airport):
    g = AirportGraph(data=airport.raw_data)
    assert g.data is airport.raw_data
    assert g.graph.number_of_nodes() == len(airport.raw_data["nodes"])


def test_init_requires_source():
    with pytest.raises(ValueError):
        AirportGraph()


# ---- Node / edge counts (parametrised) -------------------------------------

def test_node_count_matches_json(airport):
    assert (
        airport.graph.graph.number_of_nodes() == len(airport.raw_data["nodes"])
    ), f"[{airport.icao}] node count mismatch"


def test_edge_count_doubles_twoway(airport):
    # AirportGraph builds an nx.DiGraph, which deduplicates (start, end)
    # pairs. We replicate that dedup here: each twoway edge contributes
    # (s,t) and (t,s); each oneway contributes (s,t); duplicates collapse.
    # Edges referencing missing node_ids are silently dropped by the builder.
    node_ids = {str(n["node_id"]) for n in airport.raw_data["nodes"]}
    seen = set()
    for e in airport.raw_data["edges"]:
        s = str(e["start_node_id"])
        t = str(e["end_node_id"])
        if s not in node_ids or t not in node_ids:
            continue
        seen.add((s, t))
        if e.get("direction", "twoway").lower() == "twoway":
            seen.add((t, s))
    expected = len(seen)
    assert airport.graph.graph.number_of_edges() == expected, (
        f"[{airport.icao}] expected {expected} directed edges, got "
        f"{airport.graph.graph.number_of_edges()}"
    )


# ---- Haversine weights -----------------------------------------------------

def test_calculate_distance_one_degree_latitude(airport):
    # 1 degree of latitude ~= R * pi/180 ~= 111194.93 m. Identity check --
    # independent of which airport's graph is loaded.
    d = airport.graph._calculate_distance(0.0, 0.0, 1.0, 0.0)
    expected = 6371000 * math.pi / 180
    assert abs(d - expected) < 1.0


def test_calculate_distance_zero_for_same_point(airport):
    assert airport.graph._calculate_distance(42.9, -8.4, 42.9, -8.4) == 0.0


def test_edge_weights_positive_and_finite(airport):
    for u, v, data in airport.graph.graph.edges(data=True):
        w = data.get("weight")
        assert w is not None, f"[{airport.icao}] edge {u}->{v} has no weight"
        assert 0 < w < 1e6, (
            f"[{airport.icao}] edge {u}->{v} weight out of range: {w}"
        )


# ---- Secondary indices -----------------------------------------------------

def test_taxiway_index_contains_expected_subset(airport):
    keys = set(airport.graph._nodes_by_taxiway.keys())
    missing = airport.expected_taxiway_subset - keys
    assert not missing, (
        f"[{airport.icao}] missing taxiway index entries: {sorted(missing)}"
    )


def test_runway_index_has_expected_designators(airport):
    keys = set(airport.graph._runways_by_id.keys())
    missing = airport.expected_runway_ids - keys
    assert not missing, (
        f"[{airport.icao}] missing runway index entries: {sorted(missing)}"
    )
    for rwy in airport.expected_runway_ids:
        lat, lon = airport.graph._runways_by_id[rwy]
        assert -90 <= lat <= 90 and -180 <= lon <= 180


def test_stand_index_non_empty(airport):
    assert len(airport.graph._stands_by_id) > 0, (
        f"[{airport.icao}] no stands indexed"
    )


def test_main_connected_component_is_largest(airport):
    sizes = sorted(
        (len(c) for c in nx.weakly_connected_components(airport.graph.graph)),
        reverse=True,
    )
    assert len(airport.graph._main_cc) == sizes[0]
    assert len(airport.graph._main_cc) > 10


# ---- find_nearest_node -----------------------------------------------------

def test_find_nearest_node_on_known_coord(airport):
    # Pick any node in the main CC and snap to its own coordinates -> should
    # return that same node with distance 0.
    node_id = next(iter(airport.graph._main_cc))
    node = airport.graph.graph.nodes[node_id]
    found, dist = airport.graph.find_nearest_node(node["lat"], node["lon"])
    assert found == node_id
    assert dist < 1.0


def test_find_nearest_node_restrict_to_main_cc(airport):
    main_cc = airport.graph._main_cc
    lats = [airport.graph.graph.nodes[n]["lat"] for n in main_cc]
    lons = [airport.graph.graph.nodes[n]["lon"] for n in main_cc]
    cx, cy = sum(lats) / len(lats), sum(lons) / len(lons)
    found, _ = airport.graph.find_nearest_node(
        cx, cy, restrict_to_main_cc=True,
    )
    assert found is not None
    assert found in main_cc


# ---- Airport-specific: documented defect (single airport is enough) --------

@pytest.mark.xfail(
    reason="graph.py:174 has a precedence bug: "
    "`return nearest_node, min_distance if nearest_node else (None, None)` "
    "returns a nested tuple (None, (None, None)) when no match. "
    "Bug documented for memoria 5.3.3."
)
def test_find_nearest_node_returns_clean_none_when_out_of_range(lebl_graph):
    found, dist = lebl_graph.find_nearest_node(0.0, 0.0, max_distance=1000.0)
    assert found is None
    assert dist is None
