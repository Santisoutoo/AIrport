from pydantic import BaseModel


class FlightPlanResponse(BaseModel):
    """Response model matching shared/models/aircraft.py FlightPlan"""

    aircraft_registration: str
    flight_rules: str
    flight_type: str
    aircraft_type: str
    wake_turbulence_category: str = ""
    equipment: str
    transponder: str
    departure_ICAO: str
    departure_time: int
    cruising_speed: int
    cruising_altitude: int
    route: str
    destination_ICAO: str
    total_EET: str
    alternate_ICAO: str
    second_alternate_ICAO: str
    other_info: str
    endurance: str
    people_on_board: str
    remarks: str = ""
    PIC_name: str


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    version: str
    db_connected: bool = False
