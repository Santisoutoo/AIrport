import os
import logging

from fastapi import APIRouter, HTTPException
import httpx

logger = logging.getLogger(__name__)

router = APIRouter()

FLIGHT_PLAN_URL = os.getenv(
    "FLIGHT_PLAN_SERVICE_URL",
    "http://airport_flight_plan:8000"
)
WEATHER_URL = os.getenv(
    "WEATHER_SERVICE_URL",
    "http://airport_weather:8000"
)

AIRPORT_ICAO = "LEST"


@router.get("/health")
async def health_check():
    """Health check including upstream service status"""
    fp_ok = await _check_upstream(f"{FLIGHT_PLAN_URL}/api/v1/flight-plan/health")
    wx_ok = await _check_upstream(f"{WEATHER_URL}/api/v1/weather/health")
    all_ok = fp_ok and wx_ok
    return {
        "status": "healthy" if all_ok else "degraded",
        "service": "controller_hmi_service",
        "version": "1.0.0",
        "upstreams": {
            "flight_plan_service": "ok" if fp_ok else "unreachable",
            "weather_service": "ok" if wx_ok else "unreachable",
        },
    }


@router.get("/strips")
async def get_flight_strips():
    """Proxy: fetch all flight plans for strip rendering"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{FLIGHT_PLAN_URL}/api/v1/flight-plan/plans"
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Failed to fetch flight plans: %s", e)
            raise HTTPException(
                status_code=502, detail="Flight plan service unavailable"
            )


@router.get("/weather")
async def get_weather():
    """Proxy: fetch METAR for LEST"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{WEATHER_URL}/api/v1/weather/metar/{AIRPORT_ICAO}"
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Failed to fetch weather: %s", e)
            raise HTTPException(
                status_code=502, detail="Weather service unavailable"
            )


@router.get("/taf")
async def get_taf():
    """Proxy: fetch raw TAF for LEST"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{WEATHER_URL}/api/v1/weather/taf/{AIRPORT_ICAO}/raw"
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Failed to fetch TAF: %s", e)
            raise HTTPException(
                status_code=502, detail="Weather service unavailable"
            )


@router.get("/atis")
async def get_atis():
    """Proxy: fetch latest ATIS for LEST"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{WEATHER_URL}/api/v1/weather/atis/{AIRPORT_ICAO}/latest"
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Failed to fetch ATIS: %s", e)
            raise HTTPException(
                status_code=502, detail="Weather service unavailable"
            )


async def _check_upstream(url: str) -> bool:
    """Check if an upstream service is reachable"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            return resp.status_code == 200
    except Exception:
        return False
