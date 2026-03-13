import os
import sys
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
import httpx

logger = logging.getLogger(__name__)

router = APIRouter()

# Locate data/scripts dir: Docker mount or local dev path
_DOCKER_SCRIPTS = Path("/app/data_scripts")
if _DOCKER_SCRIPTS.exists():
    _SCRIPTS_DIR = _DOCKER_SCRIPTS
else:
    _SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "data" / "scripts"

if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from airport_graph_builder import AirportMapVisualizer
from airport_data_fetcher import XPlaneAirportDownloader

# Cache parsed airport graphs: { "ICAO": graph_data_dict }
_airport_graph_cache: dict = {}

FLIGHT_PLAN_URL = os.getenv(
    "FLIGHT_PLAN_SERVICE_URL",
    "http://airport_flight_plan:8000"
)
WEATHER_URL = os.getenv(
    "WEATHER_SERVICE_URL",
    "http://airport_weather:8000"
)

current_airport = {"icao": "LEST"}

# In-memory strip states: { "aircraft_reg": { "phase": "PRE_TAXI|PUSHBACK|TAXI|LINEUP|CLEARED", "column": "PRE_TAXI|TAXI|RUNWAY" } }
strip_states: dict = {}


@router.get("/airport")
async def get_airport():
    """Return current airport ICAO"""
    return current_airport


@router.post("/airport")
async def set_airport(data: dict):
    """Set current airport ICAO (called by X-Plane plugin)"""
    current_airport['icao'] = data["icao"]
    return current_airport


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
    """Proxy: fetch METAR for current airport"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{WEATHER_URL}/api/v1/weather/metar/{current_airport['icao']}"
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
    """Proxy: fetch raw TAF for current airport"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{WEATHER_URL}/api/v1/weather/taf/{current_airport['icao']}/raw"
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
    """Proxy: fetch latest ATIS for current airport"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{WEATHER_URL}/api/v1/weather/atis/{current_airport['icao']}/latest"
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Failed to fetch ATIS: %s", e)
            raise HTTPException(
                status_code=502, detail="Weather service unavailable"
            )


@router.post("/atis/generate")
async def generate_atis(data: dict):
    """Generate a new ATIS for the current airport with ATC-provided parameters"""
    arrival_runway = data.get("arrival_runway") or None
    departure_runway = data.get("departure_runway") or None
    approach = data.get("approach") or None

    params = {}
    if arrival_runway:
        params["arrival_runway"] = arrival_runway
    if departure_runway:
        params["departure_runway"] = departure_runway
    if approach:
        params["approach"] = approach

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(
                f"{WEATHER_URL}/api/v1/weather/atis/{current_airport['icao']}",
                params=params,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Failed to generate ATIS: %s", e)
            raise HTTPException(
                status_code=502, detail="Weather service unavailable"
            )


@router.get("/strips/states")
async def get_strip_states():
    """Return all strip states"""
    return strip_states


@router.patch("/strips/{aircraft_reg}/state")
async def update_strip_state(aircraft_reg: str, data: dict):
    """Update a strip's phase and column assignment"""
    phase = data.get("phase", "PRE_TAXI")
    column_map = {
        "PRE_TAXI": "PRE_TAXI",
        "PUSHBACK": "PRE_TAXI",
        "TAXI": "TAXI",
        "LINEUP": "RUNWAY",
        "CLEARED": "RUNWAY",
    }
    column = column_map.get(phase, "PRE_TAXI")
    strip_states[aircraft_reg] = {"phase": phase, "column": column}
    return strip_states[aircraft_reg]


@router.get("/airport/graph")
async def get_airport_graph():
    """Return parsed airport graph (nodes, edges, stands, runways) for SMR map"""
    icao = current_airport["icao"]

    # Return cached data if available
    if icao in _airport_graph_cache:
        return _airport_graph_cache[icao]

    dat_path = _SCRIPTS_DIR / "airport_data" / icao / f"{icao}.dat"
    if not dat_path.exists():
        logger.info("Downloading airport data for %s ...", icao)
        try:
            dl = XPlaneAirportDownloader(icao, output_directory=_SCRIPTS_DIR / "airport_data")
            result = dl.download(verbose=True)
            if result is None:
                raise HTTPException(status_code=404, detail=f"Airport {icao} not found in gateway")
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to download airport data for %s: %s", icao, e)
            raise HTTPException(status_code=502, detail=f"Failed to download airport data: {e}")

    try:
        viz = AirportMapVisualizer(str(dat_path), parse_only=True)
        graph_data = viz.get_graph_data()
        _airport_graph_cache[icao] = graph_data
        return graph_data
    except Exception as e:
        logger.error("Failed to parse airport data for %s: %s", icao, e)
        raise HTTPException(status_code=500, detail=f"Failed to parse airport data: {e}")


async def _check_upstream(url: str) -> bool:
    """Check if an upstream service is reachable"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            return resp.status_code == 200
    except Exception:
        return False
