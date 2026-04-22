"""Plan the pushback leg that precedes the taxi route.

The plane is at a stand (lat/lon/heading known); the clearance says
"pushback approved face DIRECTION". The target point for the pushback is
the first A*-path waypoint (i.e. the line where the taxi will start).
"""

import math
from dataclasses import dataclass
from typing import Optional

from . import config


@dataclass
class PushbackLeg:
    target_lat: float
    target_lon: float
    final_heading_deg: float
    distance_m: float
    speed_kts: float
    pivot_deg_per_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            "mode": "pushback",
            "target_lat": self.target_lat,
            "target_lon": self.target_lon,
            "final_heading_deg": self.final_heading_deg,
            "distance_m": round(self.distance_m, 2),
            "speed_kts": self.speed_kts,
            "pivot_deg_per_s": self.pivot_deg_per_s,
        }


_EARTH_R = 6371000.0


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _advance_point(lat: float, lon: float, bearing_deg: float, dist_m: float) -> tuple[float, float]:
    phi1 = math.radians(lat)
    lam1 = math.radians(lon)
    theta = math.radians(bearing_deg)
    delta = dist_m / _EARTH_R
    phi2 = math.asin(
        math.sin(phi1) * math.cos(delta)
        + math.cos(phi1) * math.sin(delta) * math.cos(theta)
    )
    lam2 = lam1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi1),
        math.cos(delta) - math.sin(phi1) * math.sin(phi2),
    )
    return math.degrees(phi2), math.degrees(lam2)


def plan_pushback_leg(
    stand_lat: float,
    stand_lon: float,
    stand_heading_deg: float,
    first_wp_lat: Optional[float] = None,
    first_wp_lon: Optional[float] = None,
    direction_deg: Optional[float] = None,
) -> PushbackLeg:
    """Build the pushback leg.

    - `direction_deg` is the heading the aircraft will end up pointing at
      (from "face DIRECTION"). If unknown, we fall back to a classic
      back-out: 180° relative to the stand heading.
    - When a first taxi waypoint is provided, the target is that waypoint
      (distance clamped to [MIN, MAX]). This is used when pushback is
      issued alongside a taxi clearance.
    - When no waypoint is provided (pushback-only clearance), the target
      is synthesised by back-stepping from the stand in the direction
      opposite to the final heading — the classic "back out and face
      DIRECTION" maneuver — for PUSHBACK_MIN_DIST_M metres.
    """
    if direction_deg is None:
        final_hdg = (stand_heading_deg + 180.0) % 360.0
    else:
        final_hdg = direction_deg % 360.0

    if first_wp_lat is None or first_wp_lon is None:
        # Pushback-only: back-step opposite of the final heading.
        back_bearing = (final_hdg + 180.0) % 360.0
        dist = config.PUSHBACK_MIN_DIST_M
        tgt_lat, tgt_lon = _advance_point(stand_lat, stand_lon, back_bearing, dist)
    else:
        tgt_lat, tgt_lon = first_wp_lat, first_wp_lon
        dist = _haversine_m(stand_lat, stand_lon, first_wp_lat, first_wp_lon)
        dist = max(config.PUSHBACK_MIN_DIST_M, min(config.PUSHBACK_MAX_DIST_M, dist))

    return PushbackLeg(
        target_lat=tgt_lat,
        target_lon=tgt_lon,
        final_heading_deg=final_hdg,
        distance_m=dist,
        speed_kts=config.PUSHBACK_SPEED_KTS,
        pivot_deg_per_s=config.PUSHBACK_PIVOT_DEG_PER_S,
    )
