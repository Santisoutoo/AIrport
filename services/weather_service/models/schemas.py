from datetime import datetime
from typing import Optional

from fastapi import Query
from pydantic import BaseModel


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


class ATISOptions(BaseModel):
    """ATC overrides for ``GET /atis/{icao_code}``.

    Everything the controller can set on a broadcast, grouped so the endpoint
    signature stays short (issue #64). All fields are optional: whatever is not
    provided is derived from the METAR (runways, approach) or defaults to the
    values below.

    Bound to the request through :meth:`as_query`, which keeps the endpoint a
    plain query-string GET — same parameter names, defaults and descriptions as
    before, so existing clients (HMI proxy, X-Plane plugin, scripts) are
    unaffected. The adapter is used instead of FastAPI's native query models
    because the service image pins ``fastapi==0.109.0``, which predates them.
    """

    departure_runway: Optional[str] = None
    arrival_runway: Optional[str] = None
    approach: Optional[str] = None
    qfe: Optional[int] = None
    include_tl: bool = True
    include_ta: bool = True
    remarks: Optional[str] = None
    preview: bool = False

    @classmethod
    def as_query(
        cls,
        departure_runway: Optional[str] = Query(None, description="Departure runway"),
        arrival_runway: Optional[str] = Query(None, description="Arrival runway"),
        approach: Optional[str] = Query(None, description="Approach type"),
        qfe: Optional[int] = Query(None, description="QFE in hPa (set by ATC)"),
        include_tl: bool = Query(True, description="Include Transition Level in ATIS"),
        include_ta: bool = Query(True, description="Include Transition Altitude in ATIS"),
        remarks: Optional[str] = Query(None, description="ATC remarks (appended as RMK)"),
        preview: bool = Query(False, description="Preview mode: no DB save, letter not incremented"),
    ) -> "ATISOptions":
        """FastAPI dependency: collect the query string into an ``ATISOptions``."""
        return cls(
            departure_runway=departure_runway,
            arrival_runway=arrival_runway,
            approach=approach,
            qfe=qfe,
            include_tl=include_tl,
            include_ta=include_ta,
            remarks=remarks,
            preview=preview,
        )


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
