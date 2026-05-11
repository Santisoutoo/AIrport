"""Sanity tests for the shared geodesy helpers."""

import math

from shared.services.geo import (
    advance,
    bearing,
    haversine,
    project_on_localizer,
    shortest_angle,
    NM_TO_M,
)


def test_haversine_zero():
    assert haversine(10.0, 20.0, 10.0, 20.0) == 0.0


def test_haversine_one_degree_north():
    # ~1° of latitude ≈ 111 km
    d = haversine(0.0, 0.0, 1.0, 0.0)
    assert 110_000 < d < 112_000


def test_bearing_north():
    # Going due north
    b = bearing(0.0, 0.0, 1.0, 0.0)
    assert abs(b - 0.0) < 0.01 or abs(b - 360.0) < 0.01


def test_bearing_east():
    b = bearing(0.0, 0.0, 0.0, 1.0)
    assert abs(b - 90.0) < 0.01


def test_advance_roundtrip():
    # Advance 1000m east, then haversine should give back 1000m.
    new_lat, new_lon = advance(42.0, -8.0, 90.0, 1000.0)
    d = haversine(42.0, -8.0, new_lat, new_lon)
    assert 999 < d < 1001


def test_shortest_angle():
    assert shortest_angle(10.0, 20.0) == 10.0
    assert shortest_angle(350.0, 10.0) == 20.0
    assert shortest_angle(10.0, 350.0) == -20.0


def test_project_on_localizer_rwy17():
    """Spawn point for RWY 17 should be ~10 NM to the NORTH of the threshold."""
    # LEST RWY 17 threshold + heading 169° → spawn lies on bearing 169+180 = 349° (north).
    threshold_lat, threshold_lon = 42.91180046, -8.42033176
    spawn_lat, spawn_lon = project_on_localizer(threshold_lat, threshold_lon, 169.0, 10.0)
    dist = haversine(spawn_lat, spawn_lon, threshold_lat, threshold_lon)
    assert abs(dist - 10.0 * NM_TO_M) < 5.0
    # Spawn should be north of threshold (greater latitude).
    assert spawn_lat > threshold_lat
