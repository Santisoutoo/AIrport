from typing import Optional

from db.connection import get_db
from db.repository import ClearanceRepository
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1/orchestrator/arrivals", tags=["arrivals"])


class ArrivalRegistration(BaseModel):
    aircraft_registration: str
    callsign: Optional[str] = None
    aircraft_type: Optional[str] = None
    destination_icao: str = "LEST"
    runway_in_use: str = "17"
    session_id: Optional[str] = None


@router.post("/register", status_code=201)
async def register_arrival(req: ArrivalRegistration, db: Session = Depends(get_db)):
    """Register an inbound aircraft with dependency='APP'.

    Called by the arrival_simulator at dispatch so the orchestrator's
    `_fetch_known_aircraft` sees the aircraft in BD with the right phase
    and routes the reverse handoff (advance_to_gnd_arrival) correctly.
    """
    repo = ClearanceRepository(db)
    record = repo.upsert(
        registration=req.aircraft_registration,
        session_id=req.session_id,
        squawk=2000,
        initial_altitude=0,
        instrumental_departure="",
        runway_in_use=req.runway_in_use,
        altimeter=1013.0,
        destination_icao=req.destination_icao,
        clearance_text="",
        dependency="APP",
    )
    return {
        "registered": record.aircraft_registration,
        "dependency": record.dependency,
    }
