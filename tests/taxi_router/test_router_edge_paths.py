"""Characterization tests for the router branches left uncovered (issue #49).

`tests/taxi_router/test_dispatch_taxi_plan.py` already pins the strict happy
path, the rejection path, pushback-only and destination-only clearances. What
remained uncovered — and is therefore unprotected against the `dispatch_taxi_plan`
split (issue #55) — are the degenerate and fallback branches:

  * malformed `aircraft:state` hash (position parse failure),
  * airport graph unavailable in Redis,
  * clearance without an explicit destination (last spoken taxiway wins),
  * a route that succeeds with zero waypoints,
  * a rejection whose `hmi:chat` publish blows up,
  * the whole `compute_taxi_route` entry point (strict vs lenient dispatch).

These capture the behaviour as it is today; they assert nothing about whether
that behaviour is desirable.
"""

import json

import pytest

from shared.services.taxi_router import router as router_mod
from shared.services.taxi_router.errors import RouteNotFoundError
from shared.services.taxi_router.router import compute_taxi_route, dispatch_taxi_plan

from .test_dispatch_taxi_plan import MOVE_CMD_KEY, REG, FakeRedis, _tw_nodes


@pytest.fixture()
def fake_redis(lebl_graph):
    """FakeRedis with the aircraft parked on a taxiway-E node."""
    r = FakeRedis()
    node = sorted(_tw_nodes(lebl_graph, "E") & lebl_graph._main_cc)[0]
    n = lebl_graph.graph.nodes[node]
    r.hashes[f"aircraft:state:{REG}"] = {
        "latitude": str(n["lat"]),
        "longitude": str(n["lon"]),
        "heading": "90.0",
    }
    return r


@pytest.fixture(autouse=True)
def _patch_graph(monkeypatch, lebl_graph):
    monkeypatch.setattr(router_mod, "_load_graph", lambda: lebl_graph)


def _dispatch(fake_redis, *, controller, readback="", clearance=None):
    return dispatch_taxi_plan(
        clearance or {},
        readback,
        registration=REG,
        controller_instruction=controller,
        callsign="TST123",
        delay_range_s=(0.0, 0.0),
        redis_client=fake_redis,
    )


# ---- Degenerate inputs ------------------------------------------------------


@pytest.mark.parametrize(
    "state",
    [
        pytest.param({"latitude": "not-a-number", "longitude": "2.0"}, id="unparsable"),
        pytest.param({"longitude": "2.0", "heading": "90"}, id="missing-latitude"),
    ],
)
def test_malformed_aircraft_state_is_treated_as_no_position(fake_redis, state):
    fake_redis.hashes[f"aircraft:state:{REG}"] = state
    result = _dispatch(fake_redis, controller="TST123 taxi to runway 02 via echo")
    assert result == {"success": False, "error": "no live position"}
    assert MOVE_CMD_KEY not in fake_redis.kv


def test_missing_heading_defaults_to_zero(fake_redis, lebl_graph):
    node = sorted(_tw_nodes(lebl_graph, "E") & lebl_graph._main_cc)[0]
    n = lebl_graph.graph.nodes[node]
    fake_redis.hashes[f"aircraft:state:{REG}"] = {
        "latitude": str(n["lat"]),
        "longitude": str(n["lon"]),
    }
    result = _dispatch(
        fake_redis,
        controller="TST123 pushback approved",
        clearance={"taxi_data": {"pushback_approved": True}},
    )
    assert result["success"] is True, result.get("error")


def test_graph_unavailable_aborts_without_publishing(monkeypatch, fake_redis):
    monkeypatch.setattr(
        router_mod,
        "_load_graph",
        lambda: (_ for _ in ()).throw(RouteNotFoundError("airport graph not loaded in Redis")),
    )
    result = _dispatch(fake_redis, controller="TST123 taxi to runway 02 via echo mike delta")
    assert result == {"success": False, "error": "airport graph not loaded in Redis"}
    assert MOVE_CMD_KEY not in fake_redis.kv
    assert fake_redis.published == []


# ---- Implicit destination (no endpoint spoken) ------------------------------


def test_last_spoken_taxiway_becomes_the_destination(fake_redis):
    """ "taxi via echo mike delta" with no endpoint: the route still runs
    strict over E -> M and terminates on D, which is consumed as destination
    rather than as part of the authorized sequence."""
    result = _dispatch(fake_redis, controller="TST123 taxi via echo mike delta")
    assert result["success"] is True, result.get("error")
    plan = json.loads(fake_redis.kv[MOVE_CMD_KEY])
    assert plan["strict"] is True
    seq = [str(t).upper() for t in plan["legs"][-1]["taxiway_sequence"]]
    positions = [seq.index(tw) for tw in ("E", "M", "D") if tw in seq]
    assert positions == sorted(positions), seq
    assert "D" in seq


def test_single_spoken_taxiway_is_a_lenient_destination_only_clearance(fake_redis):
    """With one token and no endpoint, the token is popped as destination and
    nothing is left to follow strictly -> the lenient A* runs."""
    result = _dispatch(fake_redis, controller="TST123 taxi via mike")
    assert result["success"] is True, result.get("error")
    plan = json.loads(fake_redis.kv[MOVE_CMD_KEY])
    assert plan["strict"] is False


# ---- Route succeeds but yields nothing to fly -------------------------------


class _EmptyRouteGraph:
    """Graph stub whose strict router reports success with no waypoints."""

    _nodes_by_taxiway = {"E": [], "M": [], "D": []}

    def find_route_strict_from_position(self, **_kwargs):
        return {"success": True, "waypoints": [], "total_distance_m": 0.0}


def test_route_without_waypoints_is_rejected_silently(monkeypatch, fake_redis):
    monkeypatch.setattr(router_mod, "_load_graph", _EmptyRouteGraph)
    result = _dispatch(fake_redis, controller="TST123 taxi to runway 02 via echo mike")
    assert result == {"success": False, "error": "empty route"}
    assert MOVE_CMD_KEY not in fake_redis.kv
    # Unlike a routing failure, this one never reaches the pilot's chat.
    assert fake_redis.published == []


# ---- Rejection publishing is best-effort ------------------------------------


def test_rejection_survives_a_broken_chat_publish(fake_redis, caplog):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("redis pubsub down")

    fake_redis.publish = _boom
    with caplog.at_level("ERROR"):
        result = _dispatch(fake_redis, controller="TST123 taxi to runway 02 via bravo delta")
    assert result["success"] is False
    assert result["reason_to_pilot_chat"] is True
    assert any("failed to publish rejection" in rec.message for rec in caplog.records)


# ---- compute_taxi_route -----------------------------------------------------


class _SpyGraph:
    """Records which routing entry point was used and with what arguments."""

    def __init__(self, result):
        self.result = result
        self.calls: list[tuple[str, dict]] = []

    def find_route_strict_from_position(self, **kwargs):
        self.calls.append(("strict", kwargs))
        return dict(self.result)

    def find_route_from_position(self, **kwargs):
        self.calls.append(("lenient", kwargs))
        return dict(self.result)


@pytest.fixture()
def positioned_redis():
    r = FakeRedis()
    r.hashes["aircraft:state:TST123"] = {
        "latitude": "41.3",
        "longitude": "2.08",
        "heading": "45.0",
    }
    return r


def test_compute_taxi_route_reports_redis_failure(monkeypatch):
    def _boom():
        raise ConnectionError("connection refused")

    monkeypatch.setattr(router_mod, "_get_redis_client", _boom)
    result = compute_taxi_route("02", [], "TST123")
    assert result["success"] is False
    assert result["error"].startswith("redis unavailable:")


def test_compute_taxi_route_reports_missing_position(monkeypatch):
    monkeypatch.setattr(router_mod, "_get_redis_client", FakeRedis)
    result = compute_taxi_route("02", [], "TST123")
    assert result["success"] is False
    assert "no live position" in result["error"]
    assert "TST123" in result["error"]


def test_compute_taxi_route_reports_graph_failure(monkeypatch, positioned_redis):
    monkeypatch.setattr(router_mod, "_get_redis_client", lambda: positioned_redis)
    monkeypatch.setattr(
        router_mod,
        "_load_graph",
        lambda: (_ for _ in ()).throw(RouteNotFoundError("airport graph not loaded in Redis")),
    )
    result = compute_taxi_route("02", ["E"], "TST123")
    assert result == {"success": False, "error": "airport graph not loaded in Redis"}


def test_compute_taxi_route_with_vias_goes_strict_and_is_not_tagged(
    monkeypatch,
    positioned_redis,
):
    spy = _SpyGraph({"success": True, "waypoints": [{"lat": 1.0, "lon": 2.0}]})
    monkeypatch.setattr(router_mod, "_get_redis_client", lambda: positioned_redis)
    monkeypatch.setattr(router_mod, "_load_graph", lambda: spy)
    result = compute_taxi_route("02", ["E", "M"], "TST123")
    assert result["success"] is True
    assert "strict" not in result  # the strict router owns its own flags
    kind, kwargs = spy.calls[0]
    assert kind == "strict"
    assert kwargs["sequence"] == ["E", "M"]
    assert kwargs["destination_token"] == "02"
    assert (kwargs["start_lat"], kwargs["start_lon"]) == (41.3, 2.08)


@pytest.mark.parametrize("via", [None, []], ids=["none", "empty"])
def test_compute_taxi_route_without_vias_is_lenient_and_tagged(
    monkeypatch,
    positioned_redis,
    via,
):
    spy = _SpyGraph({"success": True, "waypoints": [{"lat": 1.0, "lon": 2.0}]})
    monkeypatch.setattr(router_mod, "_get_redis_client", lambda: positioned_redis)
    monkeypatch.setattr(router_mod, "_load_graph", lambda: spy)
    result = compute_taxi_route("02", via, "TST123")
    assert result["strict"] is False
    kind, kwargs = spy.calls[0]
    assert kind == "lenient"
    assert kwargs["end_token"] == "02"
    assert kwargs["via"] == []


def test_compute_taxi_route_lenient_failure_is_not_tagged(monkeypatch, positioned_redis):
    spy = _SpyGraph({"success": False, "error": "no path"})
    monkeypatch.setattr(router_mod, "_get_redis_client", lambda: positioned_redis)
    monkeypatch.setattr(router_mod, "_load_graph", lambda: spy)
    result = compute_taxi_route("02", [], "TST123")
    assert result == {"success": False, "error": "no path"}


# ---- Pilot-facing phrase fallback -------------------------------------------


def test_via_point_failure_without_a_matching_token_is_generic():
    got = router_mod._shorten_reason("Could not resolve via point", ["E"], ["M"])
    assert got == "requested taxiway not found"
