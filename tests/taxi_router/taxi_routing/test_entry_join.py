"""Tests for the straight centerline join onto the first authorized taxiway.

The aircraft must enter the controller-named taxiway by projecting its
position perpendicularly onto the taxiway centerline (prolonging the nearest
segment when the foot falls beyond an endpoint) instead of cutting diagonally
to the nearest graph node — and never via an unconstrained graph search.
"""
import math

import pytest

from plugins.GND.graph import AirportGraph, project_point_to_segment

M_PER_DEG = math.pi * 6371000.0 / 180.0


def _offset(lat, lon, north_m, east_m):
    return (
        lat + north_m / M_PER_DEG,
        lon + east_m / (M_PER_DEG * math.cos(math.radians(lat))),
    )


def _haversine(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * 6371000.0 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _edge_taxiways(graph, path):
    return [
        str(graph.graph.edges[path[i], path[i + 1]].get("taxiway_id", "")).upper()
        for i in range(len(path) - 1)
    ]


def _start_node_on(graph, tw):
    nodes = sorted(
        {n for uv in graph._edges_by_taxiway[tw.upper()] for n in uv}
        & graph._main_cc
    )
    assert nodes, f"no main-CC node on taxiway {tw}"
    return nodes[0]


def _perpendicular_offset_from_edge(graph, tw, dist_m, min_len_m=60.0):
    """Pick a long twoway main-CC edge of ``tw`` and return (P, midpoint):
    P is ``dist_m`` perpendicular from the segment midpoint."""
    edges = graph._edges_by_taxiway[tw.upper()]
    for u, v in sorted(edges):
        if (v, u) not in edges:
            continue
        if u not in graph._main_cc or v not in graph._main_cc:
            continue
        if graph.graph.edges[u, v]["weight"] < min_len_m:
            continue
        nu, nv = graph.graph.nodes[u], graph.graph.nodes[v]
        mid_lat = (nu["lat"] + nv["lat"]) / 2.0
        mid_lon = (nu["lon"] + nv["lon"]) / 2.0
        # Unit vector perpendicular to the segment, in the local plane.
        ex = (nv["lon"] - nu["lon"]) * math.cos(math.radians(mid_lat))
        ey = nv["lat"] - nu["lat"]
        norm = math.hypot(ex, ey)
        p_lat, p_lon = _offset(mid_lat, mid_lon, dist_m * ex / norm, -dist_m * ey / norm)
        return (p_lat, p_lon), (mid_lat, mid_lon)
    pytest.skip(f"no suitable twoway edge on taxiway {tw}")


# ---- LEBL: real-graph behavior ----------------------------------------------

def test_entry_join_projects_perpendicularly(lebl_graph):
    (p_lat, p_lon), (mid_lat, mid_lon) = _perpendicular_offset_from_edge(
        lebl_graph, "E", 30.0,
    )
    dest = _start_node_on(lebl_graph, "M")
    r = lebl_graph.find_route_strict_from_position(p_lat, p_lon, ["E", "M"], dest)
    assert r["success"] is True, r.get("error")
    wp0 = r["waypoints"][0]
    assert wp0["node_id"] == "entry"
    assert wp0["name"] == "E entry"
    # The join point is the perpendicular foot: right at the segment midpoint,
    # 30 m from the aircraft.
    assert _haversine(wp0["lat"], wp0["lon"], mid_lat, mid_lon) < 2.0
    assert r["entry_distance_m"] == pytest.approx(30.0, abs=1.0)
    # Everything after the join stays on the authorized sequence.
    used = set(_edge_taxiways(lebl_graph, r["path_node_ids"]))
    assert used <= {"E", "M"}, f"unauthorized taxiways used: {used}"
    # path_node_ids stays graph-nodes-only; the synthetic point is only a waypoint.
    assert r["waypoints"][1]["node_id"] == r["path_node_ids"][0]


def test_entry_join_too_far_fails(lebl_graph):
    (p_lat, p_lon), _mid = _perpendicular_offset_from_edge(lebl_graph, "E", 700.0)
    # Precondition: farther than MAX_ENTRY_JOIN_M from every E edge.
    for u, v in lebl_graph._edges_by_taxiway["E"]:
        nu, nv = lebl_graph.graph.nodes[u], lebl_graph.graph.nodes[v]
        _f1, _f2, perp, _t = project_point_to_segment(
            p_lat, p_lon, nu["lat"], nu["lon"], nv["lat"], nv["lon"],
        )
        assert perp > AirportGraph.MAX_ENTRY_JOIN_M
    dest = _start_node_on(lebl_graph, "M")
    r = lebl_graph.find_route_strict_from_position(p_lat, p_lon, ["E", "M"], dest)
    assert r["success"] is False
    assert "no path from start to taxiway 'E'" in r["error"]


def test_entry_join_on_taxiway_position_is_degenerate(lebl_graph):
    # Aircraft already sitting on an E node: the join point coincides with
    # the position and the entry distance is ~0.
    start = _start_node_on(lebl_graph, "E")
    n = lebl_graph.graph.nodes[start]
    dest = _start_node_on(lebl_graph, "M")
    r = lebl_graph.find_route_strict_from_position(n["lat"], n["lon"], ["E", "M"], dest)
    assert r["success"] is True, r.get("error")
    assert r["entry_distance_m"] == pytest.approx(0.0, abs=0.5)
    wp0 = r["waypoints"][0]
    assert _haversine(wp0["lat"], wp0["lon"], n["lat"], n["lon"]) < 1.0


# ---- Synthetic graph: full control over geometry -----------------------------
#
#   1 --100m-- 2 --100m-- 3 ----K---- 4        (T: 1-2-3, K: 3-4)
#
#   5 --100m-- 6      (disconnected segment also named T, 1 km north)

LAT0, LON0 = 40.0, -3.0


def _synthetic_data(t_direction="twoway"):
    def node(nid, north_m, east_m):
        lat, lon = _offset(LAT0, LON0, north_m, east_m)
        return {"node_id": nid, "lat": lat, "lon": lon, "usage": "both", "name": f"n{nid}"}

    nodes = [
        node(1, 0, 0), node(2, 0, 100), node(3, 0, 200), node(4, 100, 200),
        node(5, 1000, 0), node(6, 1000, 100),
    ]
    edges = [
        {"start_node_id": 1, "end_node_id": 2, "direction": t_direction, "taxiway_id": "T"},
        {"start_node_id": 2, "end_node_id": 3, "direction": t_direction, "taxiway_id": "T"},
        {"start_node_id": 3, "end_node_id": 4, "direction": "twoway", "taxiway_id": "K"},
        {"start_node_id": 5, "end_node_id": 6, "direction": "twoway", "taxiway_id": "T"},
    ]
    return {"nodes": nodes, "edges": edges, "stands": [], "runways": []}


def test_synthetic_perpendicular_join_and_direction():
    g = AirportGraph(data=_synthetic_data())
    # 30 m south of the midpoint of segment 1-2.
    p_lat, p_lon = _offset(LAT0, LON0, -30.0, 50.0)
    r = g.find_route_strict_from_position(p_lat, p_lon, ["T", "K"], "4")
    assert r["success"] is True, r.get("error")
    assert r["waypoints"][0]["node_id"] == "entry"
    foot_lat, foot_lon = _offset(LAT0, LON0, 0.0, 50.0)
    assert _haversine(r["waypoints"][0]["lat"], r["waypoints"][0]["lon"], foot_lat, foot_lon) < 2.0
    assert r["entry_distance_m"] == pytest.approx(30.0, abs=1.0)
    # Correct driving direction: toward the T-K intersection (node 3).
    assert r["path_node_ids"] == ["2", "3", "4"]
    # Driven distance: 50 m along T to node 2, 100 m to 3, 100 m up K.
    assert r["total_distance_m"] == pytest.approx(250.0, abs=2.0)


def test_synthetic_join_extends_beyond_segment_end():
    g = AirportGraph(data=_synthetic_data())
    # 40 m west of node 1 (beyond the physical end of T), 10 m south: the
    # foot lies on the prolongation of segment 1-2, not at node 1.
    p_lat, p_lon = _offset(LAT0, LON0, -10.0, -40.0)
    r = g.find_route_strict_from_position(p_lat, p_lon, ["T", "K"], "4")
    assert r["success"] is True, r.get("error")
    wp0 = r["waypoints"][0]
    assert wp0["node_id"] == "entry"
    foot_lat, foot_lon = _offset(LAT0, LON0, 0.0, -40.0)
    assert _haversine(wp0["lat"], wp0["lon"], foot_lat, foot_lon) < 2.0
    assert r["entry_distance_m"] == pytest.approx(10.0, abs=1.0)
    # Entering on the prolongation, the first node crossed is 1.
    assert r["path_node_ids"] == ["1", "2", "3", "4"]


def test_synthetic_join_respects_oneway():
    g = AirportGraph(data=_synthetic_data(t_direction="oneway"))
    # Beside the midpoint of 2-3, but T is one-way 1->2->3: entry must drive
    # toward node 3, never backwards toward 2.
    p_lat, p_lon = _offset(LAT0, LON0, -30.0, 150.0)
    r = g.find_route_strict_from_position(p_lat, p_lon, ["T", "K"], "4")
    assert r["success"] is True, r.get("error")
    assert r["path_node_ids"] == ["3", "4"]


def test_synthetic_disconnected_same_name_segment_is_infeasible():
    g = AirportGraph(data=_synthetic_data())
    # Right beside the disconnected T segment (5-6): it can never reach the
    # T-K intersection, and the real T is ~1 km away — strict join must fail,
    # not wander across the graph.
    p_lat, p_lon = _offset(LAT0, LON0, 970.0, 50.0)
    r = g.find_route_strict_from_position(p_lat, p_lon, ["T", "K"], "4")
    assert r["success"] is False
    assert "no path from start to taxiway 'T'" in r["error"]
