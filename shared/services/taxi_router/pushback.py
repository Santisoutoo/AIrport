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

    def to_dict(self) -> dict:
        return {
            "mode": "pushback",
            "target_lat": self.target_lat,
            "target_lon": self.target_lon,
            "final_heading_deg": self.final_heading_deg,
            "distance_m": round(self.distance_m, 2),
            "speed_kts": self.speed_kts,
        }


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def plan_pushback_leg(
    stand_lat: float,
    stand_lon: float,
    stand_heading_deg: float,
    first_wp_lat: float,
    first_wp_lon: float,
    direction_deg: Optional[float],
) -> PushbackLeg:
    """Build the pushback leg from the stand to the first taxi waypoint.

    - `direction_deg` is the heading the aircraft will end up pointing at
      (from "face DIRECTION"). If unknown, we fall back to a classic
      back-out: 180° relative to the stand heading.
    - The distance to travel is the haversine between stand and the first
      waypoint, clamped to [PUSHBACK_MIN_DIST_M, PUSHBACK_MAX_DIST_M] so
      we don't try to cross half the apron.
    """
    if direction_deg is None:
        final_hdg = (stand_heading_deg + 180.0) % 360.0
    else:
        final_hdg = direction_deg % 360.0

    dist = _haversine_m(stand_lat, stand_lon, first_wp_lat, first_wp_lon)
    dist = max(config.PUSHBACK_MIN_DIST_M, min(config.PUSHBACK_MAX_DIST_M, dist))

    return PushbackLeg(
        target_lat=first_wp_lat,
        target_lon=first_wp_lon,
        final_heading_deg=final_hdg,
        distance_m=dist,
        speed_kts=config.PUSHBACK_SPEED_KTS,
    )
