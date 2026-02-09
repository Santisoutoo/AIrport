from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class CloudLayer(BaseModel):
    """Cloud layer information"""
    coverage: str
    base_ft: int


class ATISResponse(BaseModel):
    """ATIS response model"""

    icao_code: str
    atis_letter: str
    observation_time: datetime

    # Wind information
    wind_direction: int
    wind_speed: int
    wind_gust: Optional[int] = None
    wind_variable: bool = False
    wind_variable_from: Optional[int] = None
    wind_variable_to: Optional[int] = None

    # Horizontal visibility
    visibility_m: int

    # Weather
    weather: Optional[str] = None
    weather_description: Optional[str] = None

    # Clouds
    clouds: list[CloudLayer] = []
    ceiling_ft: Optional[int] = None
    cavok: bool = False

    # Temperature
    temperature_c: int
    dewpoint_c: int

    # Pressure
    qnh_hpa: int

    # Runway and approach
    departure_runway: Optional[str] = None
    arrival_runway: Optional[str] = None
    approach_type: Optional[str] = None
    transition_level: str
    transition_altitude: int

    # ATIS text
    remarks: Optional[str] = None
    raw_metar: str
    atis_text: str  # Full ATIS text


class ATISRequest(BaseModel):
    """Request model for generating ATIS"""
    icao_code: str
    runway_in_use: Optional[str] = None
    approach_type: Optional[str] = None


class MetarResponse(BaseModel):
    """METAR data response"""
    icao_code: str
    raw_metar: str
    observation_time: datetime
    wind_direction: int
    wind_speed: int
    wind_gust: Optional[int] = None
    visibility_m: int
    weather: Optional[str] = None
    clouds: list[CloudLayer] = []
    temperature_c: int
    dewpoint_c: int
    qnh_hpa: int
    flight_category: str


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    version: str
    db_connected: bool = False
