"""Tests for the per-taxiway edge index and intersection lookup (issue #66).

These helpers back strict routing (issue #67): `taxiway_subgraph` constrains
A* to authorized edges and `taxiway_intersections` picks real entry/exit
nodes between consecutive taxiways in a controller clearance.
"""
import pytest


# ---- _edges_by_taxiway index ------------------------------------------------

def test_edges_by_taxiway_keys_match_nodes_by_taxiway(airport):
    g = airport.graph
    assert set(g._edges_by_taxiway.keys()) == set(g._nodes_by_taxiway.keys()), (
        f"[{airport.icao}] edge and node taxiway indices diverge"
    )


def test_edges_by_taxiway_edges_exist_in_graph(airport):
    g = airport.graph
    for tw, edges in g._edges_by_taxiway.items():
        for u, v in edges:
            assert g.graph.has_edge(u, v), (
                f"[{airport.icao}] indexed edge {u}->{v} for taxiway {tw} "
                "not present in graph"
            )


def test_edges_by_taxiway_twoway_has_both_directions(airport):
    # For every indexed (u, v) whose source edge is twoway, (v, u) must be
    # indexed under the same taxiway as well.
    g = airport.graph
    for tw, edges in g._edges_by_taxiway.items():
        for u, v in edges:
            data = g.graph.edges[u, v]
            if data.get("direction", "twoway").lower() == "twoway":
                assert (v, u) in edges, (
                    f"[{airport.icao}] twoway edge {u}->{v} of {tw} missing "
                    "reverse direction in index"
                )


def test_edges_by_taxiway_endpoints_match_node_index(airport):
    # The endpoints of the indexed edges must be exactly the nodes recorded
    # in _nodes_by_taxiway for the same taxiway.
    g = airport.graph
    for tw, edges in g._edges_by_taxiway.items():
        endpoint_nodes = {n for uv in edges for n in uv}
        assert endpoint_nodes == set(g._nodes_by_taxiway[tw]), (
            f"[{airport.icao}] endpoint mismatch for taxiway {tw}"
        )


# ---- taxiway_subgraph -------------------------------------------------------

def test_taxiway_subgraph_contains_only_own_edges(airport):
    g = airport.graph
    for tw in airport.expected_taxiway_subset:
        sub = g.taxiway_subgraph(tw)
        assert sub.number_of_edges() > 0, (
            f"[{airport.icao}] empty subgraph for known taxiway {tw}"
        )
        for u, v, data in sub.edges(data=True):
            assert str(data.get("taxiway_id", "")).upper() == tw, (
                f"[{airport.icao}] foreign edge {u}->{v} "
                f"({data.get('taxiway_id')!r}) in subgraph of {tw}"
            )


def test_taxiway_subgraph_case_insensitive(airport):
    g = airport.graph
    tw = next(iter(airport.expected_taxiway_subset))
    upper = g.taxiway_subgraph(tw.upper())
    lower = g.taxiway_subgraph(tw.lower())
    assert set(upper.edges()) == set(lower.edges())


def test_taxiway_subgraph_unknown_taxiway_is_empty(airport):
    sub = airport.graph.taxiway_subgraph("ZZ99")
    assert sub.number_of_edges() == 0


# ---- taxiway_intersections --------------------------------------------------

def _adjacent_taxiway_pair(graph):
    """Find a real pair of distinct taxiways sharing at least one node."""
    membership: dict[str, set] = {}
    for tw, edges in graph._edges_by_taxiway.items():
        for u, v in edges:
            membership.setdefault(u, set()).add(tw)
            membership.setdefault(v, set()).add(tw)
    for node, tws in membership.items():
        if len(tws) >= 2:
            a, b = sorted(tws)[:2]
            return a, b
    return None


def test_taxiway_intersections_adjacent_pair_non_empty(airport):
    pair = _adjacent_taxiway_pair(airport.graph)
    assert pair is not None, f"[{airport.icao}] no adjacent taxiway pair found"
    a, b = pair
    nodes = airport.graph.taxiway_intersections(a, b)
    assert nodes, f"[{airport.icao}] {a} and {b} share nodes but lookup is empty"
    # Every reported node must be an endpoint of edges of both taxiways
    for n in nodes:
        assert n in airport.graph._nodes_by_taxiway[a]
        assert n in airport.graph._nodes_by_taxiway[b]


def test_taxiway_intersections_non_touching_pair_empty(airport):
    g = airport.graph
    # Find two taxiways with disjoint node sets
    tws = list(airport.expected_taxiway_subset)
    for i, a in enumerate(tws):
        set_a = set(g._nodes_by_taxiway[a])
        for b in tws[i + 1:]:
            if set_a.isdisjoint(g._nodes_by_taxiway[b]):
                assert g.taxiway_intersections(a, b) == []
                return
    pytest.skip(f"[{airport.icao}] every taxiway pair in subset touches")


def test_taxiway_intersections_unknown_taxiway_empty(airport):
    tw = next(iter(airport.expected_taxiway_subset))
    assert airport.graph.taxiway_intersections(tw, "ZZ99") == []
    assert airport.graph.taxiway_intersections("ZZ99", tw) == []
