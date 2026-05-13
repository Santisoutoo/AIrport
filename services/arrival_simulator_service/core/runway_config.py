"""Runway and approach geometry for arrivals.

Fixed to LEST RWY 17. No dynamic runway selection — arrivals always land on 17.
The threshold and vacate-exit coordinates come from data/airport_data/LEST/LEST_graph.json.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RunwayConfig:
    icao: str
    runway_id: str
    threshold_lat: float
    threshold_lon: float
    heading_deg: float          # true heading aircraft fly inbound
    elevation_ft: float         # field elevation MSL
    vacate_abeam_lat: float     # point on the centerline, perpendicular to the exit
    vacate_abeam_lon: float
    vacate_exit_lat: float      # E3 or E4 turnoff node
    vacate_exit_lon: float
    vacate_exit_name: str


# LEST (Santiago de Compostela) — RWY 17
# Thresholds from LEST_graph.json runways[0]: 17 (42.91180, -8.42033), 35 (42.88381, -8.41094).
# True bearing computed from threshold coordinates: 166.19° (matches magnetic 170° with ~4° W variation).
# Field elevation ≈ 370 ft MSL.
# Vacate exit E3_start (node 8): 42.89757, -8.41706.
# Abeam-E3 = perpendicular projection of E3 onto the centerline = (42.897829, -8.415645),
# at t≈0.499 along the runway (≈1600 m from threshold 17, ~119 m west of E3).
LEST_RWY_17 = RunwayConfig(
    icao="LEST",
    runway_id="17",
    threshold_lat=42.91180046,
    threshold_lon=-8.42033176,
    heading_deg=166.19,
    elevation_ft=370.0,
    vacate_abeam_lat=42.897829,
    vacate_abeam_lon=-8.415645,
    vacate_exit_lat=42.89757383,
    vacate_exit_lon=-8.41706142,
    vacate_exit_name="E3",
)


def get_active_runway(icao: str = "LEST") -> RunwayConfig:
    """Return the fixed arrival runway for the given airport.

    Today only LEST RWY 17 is supported. Other airports raise ValueError.
    """
    if icao.upper() != "LEST":
        raise ValueError(f"Arrivals only configured for LEST; got {icao!r}")
    return LEST_RWY_17
