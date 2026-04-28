from shared.services.taxi_router import config
from shared.services.taxi_router.pushback import plan_pushback_leg


def test_known_direction_preserved():
    leg = plan_pushback_leg(
        stand_lat=41.2948, stand_lon=2.0796, stand_heading_deg=200.0,
        first_wp_lat=41.2950, first_wp_lon=2.0800,
        direction_deg=0.0,
    )
    assert leg.final_heading_deg == 0.0
    assert leg.speed_kts == config.PUSHBACK_SPEED_KTS


def test_unknown_direction_uses_180_from_stand():
    leg = plan_pushback_leg(
        stand_lat=41.2948, stand_lon=2.0796, stand_heading_deg=200.0,
        first_wp_lat=41.2950, first_wp_lon=2.0800,
        direction_deg=None,
    )
    # 200 + 180 mod 360 = 20
    assert abs(leg.final_heading_deg - 20.0) < 1e-9


def test_distance_clamped_to_min():
    # Target nearly on top of the stand
    leg = plan_pushback_leg(
        stand_lat=41.2948, stand_lon=2.0796, stand_heading_deg=200.0,
        first_wp_lat=41.29481, first_wp_lon=2.07961,
        direction_deg=0.0,
    )
    assert leg.distance_m == config.PUSHBACK_MIN_DIST_M


def test_distance_clamped_to_max():
    # Far target — haversine would give hundreds of metres
    leg = plan_pushback_leg(
        stand_lat=41.2948, stand_lon=2.0796, stand_heading_deg=200.0,
        first_wp_lat=41.3000, first_wp_lon=2.0900,
        direction_deg=0.0,
    )
    assert leg.distance_m == config.PUSHBACK_MAX_DIST_M


def test_heading_modulo_360():
    leg = plan_pushback_leg(
        stand_lat=41.2948, stand_lon=2.0796, stand_heading_deg=0.0,
        first_wp_lat=41.2950, first_wp_lon=2.0800,
        direction_deg=720.0,
    )
    assert 0.0 <= leg.final_heading_deg < 360.0


def test_pushback_only_without_waypoint_synthesises_back_out():
    # No first_wp given -> target is back-step opposite to final heading
    leg = plan_pushback_leg(
        stand_lat=41.2948, stand_lon=2.0796, stand_heading_deg=90.0,
        direction_deg=0.0,  # final heading = north
    )
    # Target should lie ~south of the stand (opposite of north)
    assert leg.target_lat < 41.2948
    assert abs(leg.final_heading_deg) < 1e-9
    assert leg.distance_m == config.PUSHBACK_MIN_DIST_M


def test_pushback_only_fallback_heading_when_direction_unknown():
    leg = plan_pushback_leg(
        stand_lat=41.2948, stand_lon=2.0796, stand_heading_deg=45.0,
    )
    # Unknown direction -> classic 180-from-stand back-out
    assert abs(leg.final_heading_deg - 225.0) < 1e-9
    assert leg.distance_m == config.PUSHBACK_MIN_DIST_M


def test_to_dict_shape():
    leg = plan_pushback_leg(
        stand_lat=41.2948, stand_lon=2.0796, stand_heading_deg=0.0,
        first_wp_lat=41.2950, first_wp_lon=2.0800,
        direction_deg=45.0,
    )
    d = leg.to_dict()
    assert d["mode"] == "pushback"
    assert d["target_lat"] == 41.2950
    assert d["target_lon"] == 2.0800
    assert d["final_heading_deg"] == 45.0
    assert "distance_m" in d and "speed_kts" in d
    assert d["pivot_deg_per_s"] == config.PUSHBACK_PIVOT_DEG_PER_S
