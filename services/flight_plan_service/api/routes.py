import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session

from models.schemas import FlightPlanResponse, HealthResponse
from core.data import AIRCRAFT_DATA, AIRPORT_DATA
from core.generator import FlightPlanGenerator
from core.api_generator import APIFlightPlanGenerator
from core.database.connection import get_db, check_connection
from core.database.repositories.flight_plan import FlightPlanRepository

logger = logging.getLogger(__name__)

generator = FlightPlanGenerator()
api_generator = APIFlightPlanGenerator()

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
health_router = APIRouter(tags=["Health"])


@health_router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint including database status"""
    db_ok = check_connection()
    return HealthResponse(
        status="healthy" if db_ok else "degraded",
        service="flight_plan_service",
        version="1.0.0",
        db_connected=db_ok,
    )


# ---------------------------------------------------------------------------
# Generation – FlightPlanDatabase.com API
# ---------------------------------------------------------------------------
api_generation_router = APIRouter(prefix="/generate", tags=["Generation - API"])


@api_generation_router.get("/api", response_model=FlightPlanResponse)
async def generate_flight_plan_api(
    destination: Optional[str] = Query(
        None,
        description="Destination ICAO code: LEBL, LEMD, LEVC or LEAL. Random if omitted.",
    ),
    departure: Optional[str] = Query(
        None,
        description="Departure ICAO (current airport). Falls back to LEST if unsupported.",
    ),
    db: Session = Depends(get_db),
):
    """
    Generate a flight plan using FlightPlanDatabase.com API for realistic routes.

    Routes are only available from LEST to LEBL, LEMD, LEVC and LEAL.
    Falls back to the local generator if the API is unavailable.
    """
    try:
        flight_plan = await api_generator.generate(destination=destination, departure=departure)
        repo = FlightPlanRepository(db)
        repo.create(flight_plan)
        return flight_plan
    except Exception as e:
        logger.warning("FlightPlanDatabase API failed (%s), falling back to local generator", e)
        try:
            flight_plan = generator.generate(departure=departure)
            repo = FlightPlanRepository(db)
            repo.create(flight_plan)
            return flight_plan
        except Exception as fallback_error:
            raise HTTPException(status_code=500, detail=str(fallback_error))


# ---------------------------------------------------------------------------
# Generation – Local (offline)
# ---------------------------------------------------------------------------
local_generation_router = APIRouter(prefix="/generate", tags=["Generation - Local"])


@local_generation_router.get("", response_model=FlightPlanResponse)
async def generate_flight_plan(
    departure: Optional[str] = Query(None, description="Departure ICAO (current airport)."),
    db: Session = Depends(get_db),
):
    """
    Generate a flight plan using the local random generator (offline).

    Aircraft, route, altitude and all other fields are generated randomly
    from built-in data tables. No external API call is made.
    """
    try:
        flight_plan = generator.generate(departure=departure)
        repo = FlightPlanRepository(db)
        repo.create(flight_plan)
        return flight_plan
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Flight Plans – CRUD
# ---------------------------------------------------------------------------
plans_router = APIRouter(prefix="/plans", tags=["Flight Plans"])


@plans_router.get("", response_model=list[FlightPlanResponse])
async def get_all_flight_plans(db: Session = Depends(get_db)):
    """Get all stored flight plans"""
    repo = FlightPlanRepository(db)
    models = repo.get_all()
    return [repo.to_response(m) for m in models]


@plans_router.get("/count")
async def get_flight_plans_count(db: Session = Depends(get_db)):
    """Get the count of stored flight plans"""
    repo = FlightPlanRepository(db)
    return {"count": repo.count()}


@plans_router.get("/{registration}", response_model=FlightPlanResponse)
async def get_flight_plan(registration: str, db: Session = Depends(get_db)):
    """Get a specific flight plan by aircraft registration"""
    repo = FlightPlanRepository(db)
    model = repo.get_by_registration(registration)
    if not model:
        raise HTTPException(status_code=404, detail=f"Flight plan for {registration} not found")
    return repo.to_response(model)


@plans_router.delete("/{registration}")
async def delete_flight_plan(registration: str, db: Session = Depends(get_db)):
    """Delete a specific flight plan"""
    repo = FlightPlanRepository(db)
    deleted = repo.delete(registration)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Flight plan for {registration} not found")
    return {"deleted": registration}


@plans_router.delete("")
async def clear_all_flight_plans(db: Session = Depends(get_db)):
    """Delete all stored flight plans"""
    repo = FlightPlanRepository(db)
    count = repo.delete_all()
    return {"deleted_count": count}


# ---------------------------------------------------------------------------
# Reference Data
# ---------------------------------------------------------------------------
reference_router = APIRouter(tags=["Reference Data"])


@reference_router.get("/aircraft-types")
async def list_aircraft_types():
    """List available aircraft types with their performance data"""
    return {"aircraft_types": [{"code": code, "speed_kts": data["speed"]} for code, data in AIRCRAFT_DATA.items()]}


@reference_router.get("/airports")
async def list_airports():
    """List available airports in the database"""
    return {"airports": [{"icao": icao, "name": data["name"]} for icao, data in AIRPORT_DATA.items()]}
