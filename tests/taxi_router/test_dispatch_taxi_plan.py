"""First test coverage for dispatch_taxi_plan (issue #71).

Uses a dict-backed fake Redis injected through the existing `redis_client=`
parameter and the real LEBL fixture graph (router._load_graph monkeypatched),
so no live Redis/network is needed.

LEBL facts used (verified against the fixture): taxiways E-M and M-D
intersect, runway 02 is reachable from taxiway D within the bounded exit
hop; taxiways B and D do not touch.
"""
import json

import pytest

from shared.services.taxi_router import router as router_mod
from shared.services.taxi_router.router import dispatch_taxi_plan


# ---- Fakes ------------------------------------------------------------------

class FakeRedis:
    """Minimal dict-backed stand-in for redis.Redis (decode_responses=True)."""

    def __init__(self):
        self.hashes: dict[str, dict] = {}
        self.kv: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.published: list[tuple[str, str]] = []
        self.lists: dict[str, list] = {}

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def set(self, key, value, ex=None):
        self.kv[key] = value
        if ex is not None:
            self.ttls[key] = ex

    def setex(self, key, ttl, value):
        self.kv[key] = value
        self.ttls[key] = ttl

    def publish(self, channel, message):
        self.published.append((channel, message))

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)


REG = "EC-TST"
MOVE_CMD_KEY = f"aircraft:{REG}:move_cmd"


def _tw_nodes(graph, tw):
    return {n for uv in graph._edges_by_taxiway[tw.upper()] for n in uv}


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


# ---- Strict happy path ------------------------------------------------------

def test_strict_dispatch_writes_plan_with_controller_sequence(fake_redis, lebl_graph):
    result = _dispatch(
        fake_redis,
        controller="TST123 taxi to runway 02 via echo mike delta",
        readback="taxi runway 02 via echo mike delta, TST123",
    )
    assert result["success"] is True, result.get("error")
    plan = json.loads(fake_redis.kv[MOVE_CMD_KEY])
    assert plan["strict"] is True
    taxi_leg = plan["legs"][-1]
    assert taxi_leg["mode"] == "waypoints"
    # First appearance of the authorized taxiways in the flown sequence
    # must honor the spoken order E -> M -> D (entry/exit hops aside).
    seq = [str(t).upper() for t in taxi_leg["taxiway_sequence"]]
    positions = [seq.index(tw) for tw in ("E", "M", "D") if tw in seq]
    assert positions == sorted(positions), seq


def test_strict_dispatch_never_uses_precomputed_taxi_route(fake_redis):
    # A poisoned precomputed sequence (unknown taxiway) must be ignored:
    # routing runs on the spoken instruction only.
    result = _dispatch(
        fake_redis,
        controller="TST123 taxi to runway 02 via echo mike delta",
        clearance={"taxi_route": {"taxiway_sequence": ["ZZ99"]}},
    )
    assert result["success"] is True, result.get("error")
    assert MOVE_CMD_KEY in fake_redis.kv


def test_readback_cannot_change_route_geometry(fake_redis):
    r1 = _dispatch(
        fake_redis,
        controller="TST123 taxi to runway 02 via echo mike delta",
        readback="taxi runway 02 via echo mike delta, TST123",
    )
    plan1 = json.loads(fake_redis.kv[MOVE_CMD_KEY])
    # Same clearance, wildly different readback -> identical waypoints
    r2 = _dispatch(
        fake_redis,
        controller="TST123 taxi to runway 02 via echo mike delta",
        readback="taxi runway 02 via november kilo lima, TST123",
    )
    plan2 = json.loads(fake_redis.kv[MOVE_CMD_KEY])
    assert r1["success"] and r2["success"]
    assert plan1["legs"][-1]["waypoints"] == plan2["legs"][-1]["waypoints"]


def test_readback_mismatch_is_logged(fake_redis, caplog):
    with caplog.at_level("WARNING"):
        _dispatch(
            fake_redis,
            controller="TST123 taxi to runway 02 via echo mike delta",
            readback="taxi runway 02 via november kilo, TST123",
        )
    assert any("readback mismatch" in rec.message for rec in caplog.records)


# ---- Strict rejection: no move_cmd, pilot says unable -----------------------

def test_non_connected_sequence_rejected_no_move_cmd(fake_redis):
    result = _dispatch(
        fake_redis,
        controller="TST123 taxi to runway 02 via bravo delta",
    )
    assert result["success"] is False
    assert result.get("reason_to_pilot_chat") is True
    assert MOVE_CMD_KEY not in fake_redis.kv
    # The simulated pilot names the offending pair on hmi:chat
    assert fake_redis.published, "no pilot chat message published"
    payload = json.loads(fake_redis.published[0][1])
    assert "unable" in payload["text"].lower()
    assert "not connected" in payload["text"]


def test_corrected_clearance_dispatches_after_rejection(fake_redis):
    bad = _dispatch(
        fake_redis, controller="TST123 taxi to runway 02 via bravo delta",
    )
    assert bad["success"] is False
    good = _dispatch(
        fake_redis, controller="TST123 taxi to runway 02 via echo mike delta",
    )
    assert good["success"] is True, good.get("error")
    assert MOVE_CMD_KEY in fake_redis.kv


# ---- Pushback-only and destination-only paths -------------------------------

def test_pushback_only_dispatches_single_leg(fake_redis):
    result = _dispatch(
        fake_redis,
        controller="TST123 pushback approved face north",
        clearance={"taxi_data": {"pushback_approved": True}},
    )
    assert result["success"] is True, result.get("error")
    assert result["legs"] == 1
    plan = json.loads(fake_redis.kv[MOVE_CMD_KEY])
    assert plan["legs"][0]["mode"] == "pushback"


def test_pushback_plus_taxi_starts_at_entry_waypoint(fake_redis, lebl_graph):
    # Aircraft parked 30 m off taxiway E: the taxi leg must begin at the
    # synthetic centerline-join waypoint ("entry"), which is also what the
    # pushback leg aims the aircraft towards.
    import math
    edges = lebl_graph._edges_by_taxiway["E"]
    u, v = next(
        (u, v) for u, v in sorted(edges)
        if (v, u) in edges
        and u in lebl_graph._main_cc and v in lebl_graph._main_cc
        and lebl_graph.graph.edges[u, v]["weight"] >= 60.0
    )
    nu, nv = lebl_graph.graph.nodes[u], lebl_graph.graph.nodes[v]
    mid_lat = (nu["lat"] + nv["lat"]) / 2.0
    mid_lon = (nu["lon"] + nv["lon"]) / 2.0
    ex = (nv["lon"] - nu["lon"]) * math.cos(math.radians(mid_lat))
    ey = nv["lat"] - nu["lat"]
    norm = math.hypot(ex, ey)
    m_per_deg = math.pi * 6371000.0 / 180.0
    off_lat = mid_lat + 30.0 * ex / norm / m_per_deg
    off_lon = mid_lon - 30.0 * ey / norm / (m_per_deg * math.cos(math.radians(mid_lat)))
    fake_redis.hashes[f"aircraft:state:{REG}"] = {
        "latitude": str(off_lat), "longitude": str(off_lon), "heading": "90.0",
    }
    result = _dispatch(
        fake_redis,
        controller="TST123 pushback approved, taxi to runway 02 via echo mike delta",
        clearance={"taxi_data": {"pushback_approved": True}},
    )
    assert result["success"] is True, result.get("error")
    plan = json.loads(fake_redis.kv[MOVE_CMD_KEY])
    assert plan["legs"][0]["mode"] == "pushback"
    taxi_leg = plan["legs"][-1]
    assert taxi_leg["mode"] == "waypoints"
    first_wp = taxi_leg["waypoints"][0]
    assert first_wp["node_id"] == "entry"
    assert first_wp["name"] == "E entry"


def test_destination_only_falls_back_lenient_flagged(fake_redis):
    result = _dispatch(
        fake_redis,
        controller="TST123 taxi to runway 02",
    )
    assert result["success"] is True, result.get("error")
    plan = json.loads(fake_redis.kv[MOVE_CMD_KEY])
    assert plan["strict"] is False


def test_no_clearance_at_all_fails(fake_redis):
    result = _dispatch(fake_redis, controller="TST123 hold position")
    assert result["success"] is False
    assert MOVE_CMD_KEY not in fake_redis.kv


def test_no_live_position_fails(lebl_graph):
    r = FakeRedis()  # no aircraft:state hash
    result = dispatch_taxi_plan(
        {}, "", registration=REG,
        controller_instruction="taxi to runway 02 via echo",
        redis_client=r,
    )
    assert result["success"] is False
    assert "position" in result["error"]
