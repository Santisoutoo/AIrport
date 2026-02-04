from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from models.schemas import FlightPlanResponse, HealthResponse
from core.generator import FlightPlanGenerator, AIRCRAFT_DATA, AIRPORT_DATA
from core.database.connection import get_db, check_connection
from core.database.repositories.flight_plan import FlightPlanRepository

router = APIRouter()
generator = FlightPlanGenerator()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint including database status"""
    db_ok = check_connection()
    return HealthResponse(
        status="healthy" if db_ok else "degraded",
        service="flight_plan_service",
        version="1.0.0",
        db_connected=db_ok
    )


@router.get("/generate", response_model=FlightPlanResponse)
async def generate_flight_plan(db: Session = Depends(get_db)):
    """
    Generate a complete flight plan automatically and store it in database.
    """
    try:
        flight_plan = generator.generate()
        repo = FlightPlanRepository(db)
        repo.create(flight_plan)
        return flight_plan
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/plans", response_model=list[FlightPlanResponse])
async def get_all_flight_plans(db: Session = Depends(get_db)):
    """Get all stored flight plans"""
    repo = FlightPlanRepository(db)
    models = repo.get_all()
    return [repo.to_response(m) for m in models]


@router.get("/plans/count")
async def get_flight_plans_count(db: Session = Depends(get_db)):
    """Get the count of stored flight plans"""
    repo = FlightPlanRepository(db)
    return {"count": repo.count()}


@router.get("/plans/{registration}", response_model=FlightPlanResponse)
async def get_flight_plan(registration: str, db: Session = Depends(get_db)):
    """Get a specific flight plan by aircraft registration"""
    repo = FlightPlanRepository(db)
    model = repo.get_by_registration(registration)
    if not model:
        raise HTTPException(status_code=404, detail=f"Flight plan for {registration} not found")
    return repo.to_response(model)


@router.delete("/plans/{registration}")
async def delete_flight_plan(registration: str, db: Session = Depends(get_db)):
    """Delete a specific flight plan"""
    repo = FlightPlanRepository(db)
    deleted = repo.delete(registration)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Flight plan for {registration} not found")
    return {"deleted": registration}


@router.delete("/plans")
async def clear_all_flight_plans(db: Session = Depends(get_db)):
    """Delete all stored flight plans"""
    repo = FlightPlanRepository(db)
    count = repo.delete_all()
    return {"deleted_count": count}


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
