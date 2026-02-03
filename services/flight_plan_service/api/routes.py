from fastapi import APIRouter, HTTPException

from models.schemas import FlightPlanResponse, HealthResponse
from core.generator import FlightPlanGenerator, AIRCRAFT_DATA, AIRPORT_DATA

router = APIRouter()
generator = FlightPlanGenerator()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        service="flight_plan_service",
        version="1.0.0"
    )


@router.get("/generate", response_model=FlightPlanResponse)
async def generate_flight_plan():
    """
    Generate a complete flight plan automatically.

    All fields are auto-generated:
    - Random aircraft type and registration
    - Random departure and destination airports
    - Appropriate flight rules based on aircraft
    - Calculated route, altitude, and times
    """
    try:
        flight_plan = generator.generate()
        return flight_plan
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/aircraft-types")
async def list_aircraft_types():
    """List available aircraft types with their performance data"""
    return {
        "aircraft_types": [
            {"code": code, "speed_kts": data["speed"]}
            for code, data in AIRCRAFT_DATA.items()
        ]
    }


@router.get("/airports")
async def list_airports():
    """List available airports in the database"""
    return {
        "airports": [
            {"icao": icao, "name": data["name"]}
            for icao, data in AIRPORT_DATA.items()
        ]
    }
