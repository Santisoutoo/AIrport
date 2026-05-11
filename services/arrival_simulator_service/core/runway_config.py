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
    vacate_exit_lat: float      # E3 or E4 turnoff node
    vacate_exit_lon: float
    vacate_exit_name: str


# LEST (Santiago de Compostela) — RWY 17
# Threshold 17 from LEST_graph.json runways[0]: lat 42.91180046, lon -8.42033176.
# Heading: pista 17 → magnetic 170°; LEST magnetic variation ≈ -1° → true ≈ 169°.
# Field elevation ≈ 370 ft MSL.
# Vacate exit E3_start (node 8): lat 42.89757383, lon -8.41706142.
LEST_RWY_17 = RunwayConfig(
    icao="LEST",
    runway_id="17",
    threshold_lat=42.91180046,
    threshold_lon=-8.42033176,
    heading_deg=169.0,
    elevation_ft=370.0,
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
