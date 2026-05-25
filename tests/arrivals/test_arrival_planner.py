"""Tests for arrival plan dispatch (with Redis mocked)."""

import json
from unittest.mock import patch

from core import arrival_planner
from core.runway_config import LEST_RWY_17


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def set(self, key: str, value: str) -> None:
        self.store[key] = value


def test_dispatch_arrival_publishes_spawn_and_move_cmd():
    fake = _FakeRedis()
    plan = {
        "aircraft_registration": "EC-TEST",
        "callsign": "VLG1234",
        "aircraft_type": "A320",
    }
    with patch.object(arrival_planner, "_redis_client", return_value=fake):
        meta = arrival_planner.dispatch_arrival(plan, LEST_RWY_17)

    assert meta["registration"] == "EC-TEST"
    assert meta["runway"] == "17"
    assert "aircraft:spawn_request:EC-TEST" in fake.store
    assert "aircraft:EC-TEST:move_cmd" in fake.store

    spawn = json.loads(fake.store["aircraft:spawn_request:EC-TEST"])
    assert spawn["on_ground"] is False
    assert spawn["aircraft_type"] == "A320"
    # Spawn altitude = SPAWN_ALTITUDE_AGL_FT (5000 ft) + LEST field elev (~370 ft) = ~5370 MSL.
    # The exact constant lives in core.arrival_planner and is read from
    # the env var ARRIVAL_SPAWN_ALT_AGL_FT (default 5000.0).
    assert 5300 < spawn["altitude_msl_ft"] < 5400
    # Spawn must be NORTH of threshold (RWY 17 -> inbound from north).
    assert spawn["latitude"] > LEST_RWY_17.threshold_lat

    move = json.loads(fake.store["aircraft:EC-TEST:move_cmd"])
    assert move["version"] == 2
    modes = [leg["mode"] for leg in move["legs"]]
    assert modes == ["approach", "landing_roll", "vacate"]

    approach_leg = move["legs"][0]
    assert approach_leg["target_lat"] == LEST_RWY_17.threshold_lat
    assert approach_leg["target_lon"] == LEST_RWY_17.threshold_lon
    assert approach_leg["request_landing_at_nm"] == 4.0
    assert approach_leg["vs_fpm"] < 0  # descending

    vacate_leg = move["legs"][2]
    assert vacate_leg["mode"] == "vacate"
    # Vacate leg has two waypoints: abeam point first, then the exit point.
    assert vacate_leg["waypoints"][0]["lat"] == LEST_RWY_17.vacate_abeam_lat
    assert vacate_leg["waypoints"][1]["lat"] == LEST_RWY_17.vacate_exit_lat
