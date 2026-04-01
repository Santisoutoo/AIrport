from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.connection import get_db
from db.repository import ClearanceRepository

router = APIRouter(prefix="/clearances", tags=["clearances"])


class ClearanceRequest(BaseModel):
    aircraft_registration: str
    session_id: Optional[str] = None
    squawk: int
    initial_altitude: int
    instrumental_departure: str
    runway_in_use: str
    altimeter: float
    destination_icao: str
    clearance_text: str


class DependencyUpdate(BaseModel):
    dependency: str  # DEL | GND | TWR


@router.post("", status_code=201)
async def upsert_clearance(req: ClearanceRequest, db: Session = Depends(get_db)):
    """Create or update a delivery clearance record."""
    repo = ClearanceRepository(db)
    record = repo.upsert(
        registration=req.aircraft_registration,
        session_id=req.session_id,
        squawk=req.squawk,
        initial_altitude=req.initial_altitude,
        instrumental_departure=req.instrumental_departure,
        runway_in_use=req.runway_in_use,
        altimeter=req.altimeter,
        destination_icao=req.destination_icao,
        clearance_text=req.clearance_text,
    )
    return {
        "status": "issued",
        "aircraft_registration": record.aircraft_registration,
        "squawk": record.squawk,
        "dependency": record.dependency,
        "cleared_at": record.cleared_at.isoformat() if record.cleared_at else None,
    }


@router.get("/{registration}")
async def get_clearance(registration: str, db: Session = Depends(get_db)):
    """Get the clearance record for an aircraft."""
    repo = ClearanceRepository(db)
    record = repo.get(registration)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No clearance for {registration}")
    return {
        "aircraft_registration": record.aircraft_registration,
        "session_id": record.session_id,
        "squawk": record.squawk,
        "initial_altitude": record.initial_altitude,
        "instrumental_departure": record.instrumental_departure,
        "runway_in_use": record.runway_in_use,
        "altimeter": record.altimeter,
        "destination_icao": record.destination_icao,
        "clearance_text": record.clearance_text,
        "dependency": record.dependency,
        "taxi_route": record.taxi_route,
        "cleared_at": record.cleared_at.isoformat() if record.cleared_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


@router.patch("/{registration}/dependency")
async def update_dependency(
    registration: str, body: DependencyUpdate, db: Session = Depends(get_db)
):
    """Update which controller currently owns the aircraft (DEL → GND → TWR)."""
    valid = {"DEL", "GND", "TWR"}
    if body.dependency not in valid:
        raise HTTPException(status_code=422, detail=f"dependency must be one of {valid}")
    repo = ClearanceRepository(db)
    updated = repo.update_dependency(registration, body.dependency)
    if not updated:
        raise HTTPException(status_code=404, detail=f"No clearance for {registration}")
    return {"aircraft_registration": registration, "dependency": body.dependency}
