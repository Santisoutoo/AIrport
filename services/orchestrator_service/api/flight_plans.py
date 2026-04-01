import httpx
from fastapi import APIRouter, HTTPException

from config import config

router = APIRouter(prefix="/flight-plans", tags=["flight-plans"])


@router.get("/{registration}")
async def get_flight_plan(registration: str):
    """Proxy to flight_plan_service."""
    url = f"{config.FLIGHT_PLAN_SERVICE_URL}/plans/{registration}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Flight plan not found for {registration}")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="flight_plan_service error")
    return resp.json()
