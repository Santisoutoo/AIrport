from dataclasses import dataclass

@dataclass
class FlightPlan:
    
    """Flight Plan model """

    aircraft_registration: str
    flight_rules: str
    flight_type: str
    aircraft_type: str
    equipment: str
    transponder: str
    departure_ICAO: str
    departure_time: int
    cruising_speed: int
    route: str
    destination_ICAO: str
    total_EET: str
    altenate_ICAO: str
    seconnd_alternate_ICAO: str
    other_info: str
    endurance: str
    people_on_board: str
    PIC_name: str


@dataclass
class DelClearence:
    
    aircraft_registration: str
    lat: float
    lon: float
    squawk: int
    initial_altitude: int = 6000
    intrumental_departure: str
    runway_in_use: str
    altimeter: float
    