import httpx
from fastapi import APIRouter, HTTPException

from config import config

router = APIRouter(prefix="/atis", tags=["weather"])


@router.get("/{icao}")
async def get_atis(icao: str):
    """Proxy to weather_service — returns latest ATIS for an airport."""
    url = f"{config.WEATHER_SERVICE_URL}/atis/{icao}/latest"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail=f"ATIS not found for {icao}")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="weather_service error")
    return resp.json()
