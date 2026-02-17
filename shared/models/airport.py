from dataclasses import dataclass


@dataclass
class AirportInfo:
    icao: str
    name: str
    latitude: float
    longitude: float
