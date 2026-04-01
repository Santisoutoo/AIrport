"""
Aircraft state endpoints — used by GND and TWR agents.

Redis stores real-time position snapshots (lat/lon/alt/speed) written by X-Plane.
PostgreSQL (aircraft_clearances) stores the lifecycle state (dependency, taxi_route, etc.).
"""
import json
import os
from typing import Optional

import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.connection import get_db
from db.repository import ClearanceRepository

router = APIRouter(prefix="/aircraft", tags=["aircraft"])


def _get_redis():
    return redis_lib.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(os.getenv("REDIS_DB", "0")),
        decode_responses=True,
    )


# ---------------------------------------------------------------------------
# Position (Redis — written by X-Plane plugin)
# ---------------------------------------------------------------------------

@router.get("/{registration}/position")
async def get_position(registration: str):
    """Return the latest position snapshot for an aircraft from Redis."""
    r = _get_redis()
    data = r.hgetall(f"aircraft:state:{registration}")
    if not data:
        raise HTTPException(status_code=404, detail=f"No position data for {registration}")
    return data


@router.get("/active")
async def get_active_aircraft():
    """Return the set of currently tracked aircraft registrations."""
    r = _get_redis()
    return {"registrations": list(r.smembers("aircraft:active_set"))}


# ---------------------------------------------------------------------------
# Clearance / lifecycle (PostgreSQL)
# ---------------------------------------------------------------------------

class TaxiRouteUpdate(BaseModel):
    taxi_route: dict


@router.patch("/{registration}/taxi-route")
async def update_taxi_route(
    registration: str, body: TaxiRouteUpdate, db: Session = Depends(get_db)
):
    """GND agent sets the taxi route after issuing taxi instructions."""
    record = ClearanceRepository(db).get(registration)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No clearance for {registration}")
    record.taxi_route = body.taxi_route
    db.commit()
    return {"aircraft_registration": registration, "taxi_route": record.taxi_route}


@router.get("/{registration}/clearance")
async def get_clearance(registration: str, db: Session = Depends(get_db)):
    """Any agent can read the full clearance record for an aircraft."""
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


# ---------------------------------------------------------------------------
# Airport graph (for GND taxi routing)
# ---------------------------------------------------------------------------

@router.get("/airport/{icao}/graph")
async def get_airport_graph(icao: str):
    """Return the taxiway graph JSON for an airport."""
    import pathlib
    graph_path = (
        pathlib.Path(__file__).parents[3]
        / "data" / "airport_data" / icao / f"{icao}_graph.json"
    )
    if not graph_path.exists():
        raise HTTPException(status_code=404, detail=f"No graph data for {icao}")
    return json.loads(graph_path.read_text())
