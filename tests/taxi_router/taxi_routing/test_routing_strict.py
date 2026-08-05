"""Unit tests for strict controller-sequence routing (issue #67).

find_route_strict must follow the issued taxiway sequence exactly: each leg
runs only on edges of the taxiway being traversed, vias are never skipped,
and unknown or non-connected sequences fail instead of degrading silently.

LEBL adjacency used below (from `taxiway_intersections` on the fixture):
D-K, D-M, D-N, E-J, E-K, E-L, E-M, E-N, J-Q, M-S. Taxiway B touches none
of the sampled set.
"""


def _tw_nodes(graph, tw):
    return {n for uv in graph._edges_by_taxiway[tw.upper()] for n in uv}


def _start_node_on(graph, tw):
    """A deterministic node lying on the given taxiway (in the main CC)."""
    nodes = sorted(_tw_nodes(graph, tw) & graph._main_cc)
    assert nodes, f"no main-CC node on taxiway {tw}"
    return nodes[0]


def _edge_taxiways(graph, path):
    return [str(graph.graph.edges[path[i], path[i + 1]].get("taxiway_id", "")).upper() for i in range(len(path) - 1)]


# ---- Happy path -------------------------------------------------------------


def test_strict_route_uses_only_authorized_edges(lebl_graph):
    start = _start_node_on(lebl_graph, "D")
    dest = _start_node_on(lebl_graph, "E")
    r = lebl_graph.find_route_strict(start, ["D", "M", "E"], dest)
    assert r["success"] is True, r.get("error")
    assert r["strict"] is True
    # Start is on D and destination is on E -> no entry/exit hop, so every
    # edge must belong to the authorized sequence.
    assert r["entry_distance_m"] == 0.0
    used = set(_edge_taxiways(lebl_graph, r["path_node_ids"]))
    assert used <= {"D", "M", "E"}, f"unauthorized taxiways used: {used}"


def test_strict_route_honors_sequence_order(lebl_graph):
    start = _start_node_on(lebl_graph, "D")
    dest = _start_node_on(lebl_graph, "E")
    r = lebl_graph.find_route_strict(start, ["D", "M", "E"], dest)
    assert r["success"] is True, r.get("error")
    # The order of first appearance of each authorized taxiway in the flown
    # edge sequence must match the issued order (a taxiway may be absent only
    # if its leg collapsed to a single intersection node).
    edge_tws = _edge_taxiways(lebl_graph, r["path_node_ids"])
    first_seen = {tw: edge_tws.index(tw) for tw in ("D", "M", "E") if tw in edge_tws}
    positions = [first_seen[tw] for tw in ("D", "M", "E") if tw in first_seen]
    assert positions == sorted(positions), f"issued order not honored: {edge_tws}"


def test_strict_route_repeated_taxiway_traversed_again(lebl_graph):
    # "taxi via E, M, E" — non-adjacent repeat must be preserved and flown.
    start = _start_node_on(lebl_graph, "E")
    dest = _start_node_on(lebl_graph, "E")
    r = lebl_graph.find_route_strict(start, ["E", "M", "E"], dest)
    assert r["success"] is True, r.get("error")
    used = set(_edge_taxiways(lebl_graph, r["path_node_ids"]))
    assert used <= {"E", "M"}, f"unauthorized taxiways used: {used}"


def test_strict_route_consecutive_duplicates_collapse(lebl_graph):
    # Phonetic repetition ("delta delta") must not create a zero-length leg.
    start = _start_node_on(lebl_graph, "D")
    dest = _start_node_on(lebl_graph, "M")
    r1 = lebl_graph.find_route_strict(start, ["D", "D", "M"], dest)
    r2 = lebl_graph.find_route_strict(start, ["D", "M"], dest)
    assert r1["success"] and r2["success"]
    assert r1["path_node_ids"] == r2["path_node_ids"]


def test_strict_route_destination_on_last_taxiway(lebl_graph):
    start = _start_node_on(lebl_graph, "Q")
    dest = _start_node_on(lebl_graph, "J")
    r = lebl_graph.find_route_strict(start, ["Q", "J"], dest)
    assert r["success"] is True, r.get("error")
    assert r["path_node_ids"][-1] == dest
    used = set(_edge_taxiways(lebl_graph, r["path_node_ids"]))
    assert used <= {"Q", "J"}


# ---- Strict failure modes ---------------------------------------------------


def test_strict_route_unknown_taxiway_fails_naming_token(lebl_graph):
    start = _start_node_on(lebl_graph, "D")
    r = lebl_graph.find_route_strict(start, ["D", "ZZ99"], "06R")
    assert r["success"] is False
    assert "ZZ99" in r["error"]


def test_strict_route_non_connected_pair_fails_naming_pair(lebl_graph):
    # B touches neither D nor any of the sampled taxiways at LEBL.
    assert lebl_graph.taxiway_intersections("B", "D") == []
    start = _start_node_on(lebl_graph, "B")
    dest = _start_node_on(lebl_graph, "D")
    r = lebl_graph.find_route_strict(start, ["B", "D"], dest)
    assert r["success"] is False
    assert "B" in r["error"] and "D" in r["error"]
    assert "not connected" in r["error"]


def test_strict_route_empty_sequence_fails(lebl_graph):
    r = lebl_graph.find_route_strict("0", [], "06R")
    assert r["success"] is False
    assert "empty" in r["error"]


def test_strict_route_destination_too_far_off_sequence_fails(lebl_graph):
    # Runway 24L threshold is ~1.5km away from taxiway E's nearest node:
    # the exit hop exceeds MAX_EXIT_HOP_M and must fail, not silently route.
    start = _start_node_on(lebl_graph, "M")
    r = lebl_graph.find_route_strict(start, ["M", "E"], "24L")
    assert r["success"] is False
    assert "too far" in r["error"]


def test_strict_route_invalid_start_token(lebl_graph):
    r = lebl_graph.find_route_strict("XYZ_NOT_A_TOKEN", ["D"], "06R")
    assert r["success"] is False
    assert "start token" in r["error"]


# ---- Shape compatibility with find_route_via --------------------------------


def test_strict_result_shape_matches_find_route_via(lebl_graph):
    start = _start_node_on(lebl_graph, "D")
    dest = _start_node_on(lebl_graph, "E")
    r = lebl_graph.find_route_strict(start, ["D", "M", "E"], dest)
    assert r["success"], r.get("error")
    for key in (
        "success",
        "path_node_ids",
        "waypoints",
        "taxiway_sequence",
        "total_distance_m",
        "start",
        "end",
    ):
        assert key in r, f"missing key: {key}"
    for sub in ("node_id", "lat", "lon", "token"):
        assert sub in r["start"]
        assert sub in r["end"]
    for wp in r["waypoints"]:
        assert set(wp) == {"node_id", "lat", "lon", "name"}


def test_strict_path_nodes_are_connected(lebl_graph):
    start = _start_node_on(lebl_graph, "D")
    dest = _start_node_on(lebl_graph, "E")
    r = lebl_graph.find_route_strict(start, ["D", "M", "E"], dest)
    assert r["success"], r.get("error")
    path = r["path_node_ids"]
    for i in range(len(path) - 1):
        assert lebl_graph.graph.has_edge(path[i], path[i + 1])


# ---- find_route_strict_from_position ---------------------------------------


def test_strict_from_position_snaps_and_delegates(lebl_graph):
    start = _start_node_on(lebl_graph, "Q")
    n = lebl_graph.graph.nodes[start]
    dest = _start_node_on(lebl_graph, "J")
    r = lebl_graph.find_route_strict_from_position(
        n["lat"],
        n["lon"],
        ["Q", "J"],
        dest,
    )
    assert r["success"] is True, r.get("error")
    assert r["start"]["node_id"] == start


def test_strict_from_position_no_connected_node(lebl_graph):
    r = lebl_graph.find_route_strict_from_position(0.0, 0.0, ["D"], "06R")
    assert r["success"] is False
    assert "No connected node" in r["error"]
