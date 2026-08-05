"""Geodesy helpers shared between the X-Plane mover and backend services
(arrival_simulator, taxi_router callers, etc.).

All angles are in degrees, distances in metres unless suffixed.
"""

import math

EARTH_R_M = 6371000.0
KT_TO_MPS = 0.514444
NM_TO_M = 1852.0
FT_TO_M = 0.3048


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_M * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2, degrees in [0, 360)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def advance(lat: float, lon: float, bearing_deg: float, dist_m: float) -> tuple[float, float]:
    """Move (lat, lon) by `dist_m` along `bearing_deg`. Returns new (lat, lon)."""
    if dist_m <= 0.0:
        return lat, lon
    phi1 = math.radians(lat)
    lam1 = math.radians(lon)
    theta = math.radians(bearing_deg)
    delta = dist_m / EARTH_R_M
    phi2 = math.asin(math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta))
    lam2 = lam1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi1),
        math.cos(delta) - math.sin(phi1) * math.sin(phi2),
    )
    return math.degrees(phi2), math.degrees(lam2)


def shortest_angle(cur: float, target: float) -> float:
    """Signed shortest angular difference (target - cur), in (-180, 180]."""
    return ((target - cur) + 540.0) % 360.0 - 180.0


def project_on_localizer(
    threshold_lat: float,
    threshold_lon: float,
    runway_hdg_deg: float,
    distance_nm: float,
) -> tuple[float, float]:
    """Project a point `distance_nm` out on the localizer of a runway.

    The runway heading is the direction aircraft fly inbound (e.g. 167°
    for RWY 17). The localizer extends in the opposite direction, so the
    inbound aircraft is at bearing (runway_hdg + 180) from the threshold.
    """
    outbound_bearing = (runway_hdg_deg + 180.0) % 360.0
    return advance(threshold_lat, threshold_lon, outbound_bearing, distance_nm * NM_TO_M)
