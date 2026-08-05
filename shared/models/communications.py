from dataclasses import dataclass
from enum import Enum

@dataclass
class HandOff:

    aircraft_identification: str
    dependency_from: str
    dependency_to: str
    frecuency: float

class Frequencies(Enum):

    ATIS = 121.980
    DEL = 121.805
    GND = 121.655
    TWR = 118.330
    