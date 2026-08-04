"""Unit tests for project_point_to_segment (straight centerline join).

The helper returns the perpendicular foot of a point on the infinite line
through a segment, with the along-track parameter t unclamped so callers can
prolong the segment ("prolongar la linea") when the foot falls beyond an
endpoint.
"""
import math

import pytest

from plugins.GND.graph import project_point_to_segment

# Metres per degree of latitude on the sphere used by the module (R=6371 km).
M_PER_DEG = math.pi * 6371000.0 / 180.0

LAT_A, LON_A = 42.8930, -8.4190  # LEST apron area, arbitrary


def _offset(lat, lon, north_m, east_m):
    return (
        lat + north_m / M_PER_DEG,
        lon + east_m / (M_PER_DEG * math.cos(math.radians(lat))),
    )


def test_foot_inside_segment():
    lat_b, lon_b = _offset(LAT_A, LON_A, 0.0, 200.0)  # 200 m due east
    # Point above the midpoint, 30 m north of the segment.
    p_lat, p_lon = _offset(LAT_A, LON_A, 30.0, 100.0)
    f_lat, f_lon, perp, t = project_point_to_segment(
        p_lat, p_lon, LAT_A, LON_A, lat_b, lon_b,
    )
    assert t == pytest.approx(0.5, abs=0.01)
    assert perp == pytest.approx(30.0, abs=0.5)
    mid_lat, mid_lon = _offset(LAT_A, LON_A, 0.0, 100.0)
    assert f_lat == pytest.approx(mid_lat, abs=1e-6)
    assert f_lon == pytest.approx(mid_lon, abs=1e-6)


def test_foot_beyond_endpoint_b_is_not_clamped():
    lat_b, lon_b = _offset(LAT_A, LON_A, 0.0, 100.0)
    # 50 m past B along the track, 10 m off the line.
    p_lat, p_lon = _offset(LAT_A, LON_A, 10.0, 150.0)
    _f_lat, _f_lon, perp, t = project_point_to_segment(
        p_lat, p_lon, LAT_A, LON_A, lat_b, lon_b,
    )
    assert t == pytest.approx(1.5, abs=0.01)
    assert perp == pytest.approx(10.0, abs=0.5)


def test_foot_before_endpoint_a_is_negative_t():
    lat_b, lon_b = _offset(LAT_A, LON_A, 0.0, 100.0)
    p_lat, p_lon = _offset(LAT_A, LON_A, -10.0, -50.0)
    _f_lat, _f_lon, perp, t = project_point_to_segment(
        p_lat, p_lon, LAT_A, LON_A, lat_b, lon_b,
    )
    assert t == pytest.approx(-0.5, abs=0.01)
    assert perp == pytest.approx(10.0, abs=0.5)


def test_degenerate_zero_length_segment_returns_a():
    p_lat, p_lon = _offset(LAT_A, LON_A, 30.0, 40.0)
    f_lat, f_lon, perp, t = project_point_to_segment(
        p_lat, p_lon, LAT_A, LON_A, LAT_A, LON_A,
    )
    assert (f_lat, f_lon) == (LAT_A, LON_A)
    assert perp == pytest.approx(50.0, abs=0.5)
    assert t == 0.0


def test_endpoint_order_symmetry():
    lat_b, lon_b = _offset(LAT_A, LON_A, 50.0, 150.0)
    p_lat, p_lon = _offset(LAT_A, LON_A, 40.0, 60.0)
    f1 = project_point_to_segment(p_lat, p_lon, LAT_A, LON_A, lat_b, lon_b)
    f2 = project_point_to_segment(p_lat, p_lon, lat_b, lon_b, LAT_A, LON_A)
    assert f1[0] == pytest.approx(f2[0], abs=1e-6)
    assert f1[1] == pytest.approx(f2[1], abs=1e-6)
    assert f1[2] == pytest.approx(f2[2], abs=0.5)
    assert f1[3] == pytest.approx(1.0 - f2[3], abs=0.01)
