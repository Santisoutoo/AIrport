from dataclasses import dataclass
from enum import Enum

@dataclass
class HandOff:

    aircraft_identification: str
    dependency_from: str
    dependency_to: str
    frecuency: float

class Frequencies(Enum):

    ATIS: float = 121.980
    DEL: float = 121.805
    GND: float = 121.655
    TWR: float = 118.330
    