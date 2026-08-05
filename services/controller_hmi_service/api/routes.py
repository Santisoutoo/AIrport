import os
import sys
import logging
from pathlib import Path

import redis as redis_lib
from fastapi import APIRouter, HTTPException, Request
import httpx

logger = logging.getLogger(__name__)

router = APIRouter()

_redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
_redis = redis_lib.from_url(_redis_url, decode_responses=True)

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

FLIGHT_PLAN_URL = os.getenv("FLIGHT_PLAN_SERVICE_URL", "http://airport_flight_plan:8000")
WEATHER_URL = os.getenv("WEATHER_SERVICE_URL", "http://airport_weather:8000")

current_airport = {"icao": "LEST"}

# In-memory strip states: { "aircraft_reg": { "phase": "...", "column": "..." } }
strip_states: dict = {}

# Virtual arrival strips: planes dispatched by arrival_simulator that don't
# have a DB flight plan.  Keyed by registration, value is a minimal plan dict.
_virtual_arrival_strips: dict = {}


@router.get("/airport")
async def get_airport():
    """Return current airport ICAO"""
    return current_airport


@router.post("/airport")
async def set_airport(data: dict):
    """Set current airport ICAO (called by X-Plane plugin)"""
    current_airport["icao"] = data["icao"]
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
    """Proxy: fetch all flight plans, merged with virtual arrival strips."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{FLIGHT_PLAN_URL}/api/v1/flight-plan/plans")
            resp.raise_for_status()
            db_plans = resp.json() or []
        except httpx.HTTPError as e:
            logger.error("Failed to fetch flight plans: %s", e)
            db_plans = []

    db_regs = {p["aircraft_registration"] for p in db_plans}
    virtual = [v for reg, v in _virtual_arrival_strips.items() if reg not in db_regs]
    return db_plans + virtual


@router.post("/strips/arrival")
async def register_arrival_strip(data: dict):
    """Register a virtual arrival strip (no DB flight plan required).

    Expected fields: aircraft_registration, callsign, aircraft_type,
    departure_ICAO, destination_ICAO.
    """
    reg = data.get("aircraft_registration")
    if not reg:
        raise HTTPException(status_code=422, detail="aircraft_registration required")
    _virtual_arrival_strips[reg] = {
        "aircraft_registration": reg,
        "callsign": data.get("callsign", reg),
        "aircraft_type": data.get("aircraft_type", "UNKN"),
        "flight_rules": "I",
        "flight_type": "S",
        "wake_turbulence_category": "M",
        "equipment": "S",
        "transponder": "S",
        "departure_ICAO": data.get("departure_ICAO", "ZZZZ"),
        "departure_time": 0,
        "cruising_speed": 460,
        "cruising_altitude": 35000,
        "route": "DCT",
        "destination_ICAO": data.get("destination_ICAO", "LEST"),
        "total_EET": "0100",
        "alternate_ICAO": "",
        "second_alternate_ICAO": "",
        "other_info": "",
        "endurance": "0200",
        "people_on_board": "180",
        "remarks": "ARRIVAL",
        "PIC_name": "",
    }
    # Set strip state to ARRIVALS column immediately.
    strip_states[reg] = {"phase": "approach", "column": "ARRIVALS"}
    return {"registered": reg}


@router.delete("/strips/arrival/{aircraft_reg}")
async def remove_arrival_strip(aircraft_reg: str):
    """Remove a virtual arrival strip when the aircraft parks."""
    _virtual_arrival_strips.pop(aircraft_reg, None)
    strip_states.pop(aircraft_reg, None)
    return {"removed": aircraft_reg}


@router.delete("/strips/arrivals")
async def clear_all_arrival_strips():
    """Clear ALL virtual arrival strips and their HMI states.

    Called by the X-Plane plugin at the start of every new session so that
    strips from the previous session don't persist in memory.
    """
    _virtual_arrival_strips.clear()
    dead = [reg for reg, s in strip_states.items() if s.get("column") == "ARRIVALS"]
    for reg in dead:
        strip_states.pop(reg, None)
    return {"cleared": len(dead)}


@router.get("/weather")
async def get_weather():
    """Proxy: fetch METAR for current airport"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{WEATHER_URL}/api/v1/weather/metar/{current_airport['icao']}")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Failed to fetch weather: %s", e)
            raise HTTPException(status_code=502, detail="Weather service unavailable")


@router.get("/taf")
async def get_taf():
    """Proxy: fetch raw TAF for current airport"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{WEATHER_URL}/api/v1/weather/taf/{current_airport['icao']}/raw")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Failed to fetch TAF: %s", e)
            raise HTTPException(status_code=502, detail="Weather service unavailable")


@router.get("/atis")
async def get_atis():
    """Proxy: fetch latest ATIS for current airport"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{WEATHER_URL}/api/v1/weather/atis/{current_airport['icao']}/latest")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Failed to fetch ATIS: %s", e)
            raise HTTPException(status_code=502, detail="Weather service unavailable")


@router.post("/atis/generate")
async def generate_atis(data: dict):
    """Generate a new ATIS for the current airport with ATC-provided parameters"""
    arrival_runway = data.get("arrival_runway") or None
    departure_runway = data.get("departure_runway") or None
    approach = data.get("approach") or None
    qfe = data.get("qfe") or None
    include_tl = data.get("include_tl", True)
    include_ta = data.get("include_ta", True)
    remarks = data.get("remarks") or None
    metar_station = (data.get("metar_station") or "").strip().upper() or current_airport["icao"]
    preview = bool(data.get("preview", False))

    params = {}
    if arrival_runway:
        params["arrival_runway"] = arrival_runway
    if departure_runway:
        params["departure_runway"] = departure_runway
    if approach:
        params["approach"] = approach
    if qfe:
        params["qfe"] = qfe
    params["include_tl"] = str(include_tl).lower()
    params["include_ta"] = str(include_ta).lower()
    if remarks:
        params["remarks"] = remarks
    if preview:
        params["preview"] = "true"

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(
                f"{WEATHER_URL}/api/v1/weather/atis/{metar_station}",
                params=params,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Failed to generate ATIS: %s", e)
            raise HTTPException(status_code=502, detail="Weather service unavailable")


@router.get("/aircraft/positions")
async def get_aircraft_positions():
    """Live aircraft positions from Redis state store.

    Returns a list of {registration, callsign, latitude, longitude,
    heading, phase, ground_speed} for every aircraft in the active set.
    Used by the SMR map to render dots at their real coordinates instead
    of guessing from the strip order."""
    try:
        regs = _redis.smembers("aircraft:active_set") or set()
    except Exception as exc:
        logger.error("redis unavailable: %s", exc)
        raise HTTPException(status_code=502, detail="redis unavailable")

    out = []
    for reg in regs:
        if reg == "USER":
            continue
        try:
            h = _redis.hgetall(f"aircraft:state:{reg}")
        except Exception:
            continue
        if not h:
            continue
        try:
            out.append(
                {
                    "registration": reg,
                    "callsign": h.get("callsign", reg),
                    "latitude": float(h.get("latitude", 0.0) or 0.0),
                    "longitude": float(h.get("longitude", 0.0) or 0.0),
                    "heading": float(h.get("heading", 0.0) or 0.0),
                    "ground_speed": float(h.get("ground_speed", 0.0) or 0.0),
                    "phase": h.get("phase", ""),
                }
            )
        except (TypeError, ValueError):
            continue
    return out


@router.get("/strips/states")
async def get_strip_states():
    """Return all strip states"""
    return strip_states


# LEST RWY 17 threshold (matches arrival_simulator_service runway_config).
_RUNWAY_17_LAT = 42.91180046
_RUNWAY_17_LON = -8.42033176


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math

    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    d_m = 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return d_m / 1852.0


@router.get("/strips/arrivals/{aircraft_reg}")
async def get_arrival_detail(aircraft_reg: str):
    """Live detail for an inbound aircraft: distance to threshold, altitude, IAS."""
    try:
        h = _redis.hgetall(f"aircraft:state:{aircraft_reg}")
    except Exception:
        raise HTTPException(status_code=502, detail="redis unavailable")
    if not h:
        raise HTTPException(status_code=404, detail="aircraft not in state store")

    try:
        lat = float(h.get("latitude", 0.0) or 0.0)
        lon = float(h.get("longitude", 0.0) or 0.0)
        alt_msl = float(h.get("altitude_msl", 0.0) or 0.0)
        alt_agl = float(h.get("altitude_agl", 0.0) or 0.0)
        ias = float(h.get("indicated_airspeed", 0.0) or 0.0)
        vs = float(h.get("vertical_speed", 0.0) or 0.0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=500, detail="invalid state payload")

    dme_nm = _haversine_nm(lat, lon, _RUNWAY_17_LAT, _RUNWAY_17_LON)
    eta_s = (dme_nm * 1852.0) / max(0.5, ias * 0.514444) if ias > 0 else None

    return {
        "registration": aircraft_reg,
        "callsign": h.get("callsign", aircraft_reg),
        "phase": h.get("phase", ""),
        "latitude": lat,
        "longitude": lon,
        "altitude_msl_ft": alt_msl,
        "altitude_agl_ft": alt_agl,
        "indicated_airspeed_kts": ias,
        "vertical_speed_fpm": vs,
        "distance_to_threshold_nm": round(dme_nm, 2),
        "eta_seconds": round(eta_s, 1) if eta_s is not None else None,
        "runway": "17",
    }


@router.patch("/strips/{aircraft_reg}/state")
async def update_strip_state(aircraft_reg: str, data: dict):
    """Update a strip's phase and column assignment"""
    phase = data.get("phase", "PRE_TAXI")
    # Mover emits phases in lower-case (approach, landing_roll, vacating, ...);
    # HMI uses upper-case codes (APPROACH, LANDED, VACATING). Accept both.
    column_map = {
        "PRE_TAXI": "PRE_TAXI",
        "PUSHBACK": "PRE_TAXI",
        "pushback": "PRE_TAXI",
        "parked": "PRE_TAXI",
        "TAXI": "TAXI",
        "taxi_out": "TAXI",
        "LINEUP": "RUNWAY",
        "CLEARED": "RUNWAY",
        "APPROACH": "ARRIVALS",
        "approach": "ARRIVALS",
        "short_final": "ARRIVALS",
        "LANDED": "ARRIVALS",
        "landing_roll": "ARRIVALS",
        "VACATING": "ARRIVALS",
        "vacating": "ARRIVALS",
        "taxi_in": "ARRIVALS",
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


@router.post("/asr/transcribe")
async def proxy_asr_transcribe(request: Request):
    """Proxy: forward raw multipart body to the ASR service (Cloud Run or local)."""
    asr_url = os.getenv("ASR_URL", "")
    if not asr_url:
        raise HTTPException(status_code=503, detail="ASR_URL not configured")

    body = await request.body()
    content_type = request.headers.get("content-type", "")
    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            resp = await client.post(
                f"{asr_url}/transcribe",
                content=body,
                headers={"content-type": content_type},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=str(e))
        except httpx.RequestError as e:
            logger.error("ASR proxy error: %s %r", type(e).__name__, e)
            raise HTTPException(status_code=502, detail="ASR service unreachable")


@router.post("/orchestrator/dispatch")
async def proxy_orchestrator_dispatch(request: Request):
    """Proxy: forward dispatch request to the orchestrator service."""
    orchestrator_url = os.getenv("ORCHESTRATOR_URL", "http://orchestrator_service:8006")
    body = await request.body()
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(
                f"{orchestrator_url}/dispatch",
                content=body,
                headers={"content-type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            detail = f"Orchestrator error {e.response.status_code}"
            try:
                detail = e.response.json().get("detail", detail)
            except Exception:
                pass
            logger.error("Orchestrator proxy error: %s", e)
            raise HTTPException(status_code=e.response.status_code, detail=detail)
        except httpx.RequestError as e:
            logger.error("Orchestrator proxy error: %s", e)
            raise HTTPException(status_code=502, detail="Orchestrator service unreachable")


@router.post("/debrief/generate")
async def proxy_debrief(request: Request):
    """Proxy: forward debrief generation request to the orchestrator."""
    orchestrator_url = os.getenv("ORCHESTRATOR_URL", "http://orchestrator_service:8006")
    body = await request.body()
    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            resp = await client.post(
                f"{orchestrator_url}/debrief/generate",
                content=body,
                headers={"content-type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            detail = f"Debrief error {e.response.status_code}"
            try:
                detail = e.response.json().get("detail", detail)
            except Exception:
                pass
            logger.error("Debrief proxy error: %s", e)
            raise HTTPException(status_code=e.response.status_code, detail=detail)
        except httpx.RequestError as e:
            logger.error("Debrief proxy error: %s", e)
            raise HTTPException(status_code=502, detail="Orchestrator service unreachable")


async def _check_upstream(url: str) -> bool:
    """Check if an upstream service is reachable"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            return resp.status_code == 200
    except Exception:
        return False
