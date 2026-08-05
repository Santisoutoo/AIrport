import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from models.schemas import (
    ATISOptions,
    ATISRequest,
    ATISResponse,
    CloudLayer,
    HealthResponse,
    MetarResponse,
)
from core.atis_generator import ATISGenerator
from core.metar_taf_fetcher import (
    NoWeatherDataError,
    WeatherUpstreamError,
    get_metar,
    get_taf,
)
from core.database.connection import get_db, check_connection
from core.database.repositories.atis import ATISRepository

logger = logging.getLogger(__name__)

router = APIRouter()
generator = ATISGenerator()

#: Exceptions raised while decoding an aviationweather.gov JSON payload whose
#: shape does not match what we expect (missing key, wrong type, unparsable
#: number or timestamp, ``None`` where a string was promised). They mean "bad
#: upstream data", i.e. a 502, never a 500.
MALFORMED_PAYLOAD_ERRORS = (AttributeError, IndexError, KeyError, TypeError, ValueError)


#  Health
@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint"""
    db_ok = check_connection()
    return HealthResponse(
        status="healthy" if db_ok else "degraded", service="weather_service", version="1.0.0", db_connected=db_ok
    )


#  ATIS
@router.get("/atis/{icao_code}", response_model=ATISResponse, tags=["ATIS"])
async def generate_atis(
    icao_code: str,
    options: ATISOptions = Depends(ATISOptions.as_query),
    db: Session = Depends(get_db),
):
    """Generate ATIS for an airport"""
    try:
        atis = await generator.generate(icao_code=icao_code, **options.model_dump())
    except NoWeatherDataError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except WeatherUpstreamError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except MALFORMED_PAYLOAD_ERRORS:
        logger.exception("Malformed METAR payload while generating ATIS for %s", icao_code)
        raise HTTPException(status_code=502, detail=f"Malformed METAR data for {icao_code.upper()}")

    if not options.preview:
        try:
            repo = ATISRepository(db)
            repo.create(atis)
        except SQLAlchemyError:
            logger.exception("Failed to persist ATIS for %s", icao_code)
            raise HTTPException(status_code=500, detail="Failed to store the generated ATIS")

    return atis


@router.get("/atis/{icao_code}/latest", response_model=ATISResponse, tags=["ATIS"])
async def get_latest_atis(icao_code: str, db: Session = Depends(get_db)):
    """Get the most recent stored ATIS"""
    repo = ATISRepository(db)
    model = repo.get_latest_by_icao(icao_code)
    if not model:
        raise HTTPException(status_code=404, detail=f"No ATIS found for {icao_code.upper()}")
    return repo.to_response(model)


@router.get("/atis/{icao_code}/history", response_model=list[ATISResponse], tags=["ATIS"])
async def get_atis_history(icao_code: str, limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    """Get ATIS history for an airport"""
    repo = ATISRepository(db)
    models = repo.get_all_by_icao(icao_code, limit=limit)
    return [repo.to_response(m) for m in models]


@router.delete("/atis/{icao_code}", tags=["ATIS"])
async def delete_atis_by_airport(icao_code: str, db: Session = Depends(get_db)):
    """Delete all ATIS records for an airport"""
    repo = ATISRepository(db)
    count = repo.delete_by_icao(icao_code)
    return {"deleted_count": count, "icao_code": icao_code.upper()}


#  METAR
@router.get("/metar/{icao_code}", response_model=MetarResponse, tags=["METAR"])
async def get_metar_data(icao_code: str):
    """Fetch current METAR for an airport"""
    try:
        data = await get_metar(icao_code, output_format="json")
    except WeatherUpstreamError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))

    if not data or len(data) == 0:
        raise HTTPException(status_code=404, detail=f"No METAR for {icao_code.upper()}")

    try:
        metar = data[0]

        # Wind
        wdir = metar.get("wdir")
        wind_dir = 0 if wdir == "VRB" or wdir is None else int(wdir)

        # Visibility
        raw_ob = metar.get("rawOb", "")
        visib = metar.get("visib")
        if " 9999 " in f" {raw_ob} ":
            vis_m = 9999
        elif visib:
            visib_clean = str(visib).replace("+", "")
            vis_m = min(int(float(visib_clean) * 1609.34), 9999)
        else:
            vis_m = 9999

        # Clouds
        clouds = []
        ceiling = None
        for cloud in metar.get("clouds", []):
            cover = cloud.get("cover")
            base = cloud.get("base")
            if cover and base is not None:
                clouds.append(CloudLayer(coverage=cover, base_ft=int(base)))
                if cover in ["BKN", "OVC"] and (ceiling is None or int(base) < ceiling):
                    ceiling = int(base)

        # Pressure (altim from aviationweather.gov is already in hPa)
        altim = metar.get("altim")
        qnh = int(float(altim)) if altim else 1013

        # Flight category
        flight_cat = _determine_flight_category(ceiling, vis_m)

        return MetarResponse(
            icao_code=icao_code.upper(),
            raw_metar=metar.get("rawOb", ""),
            observation_time=metar.get("reportTime", ""),
            wind_direction=wind_dir,
            wind_speed=int(metar.get("wspd", 0)),
            wind_gust=int(metar.get("wgst")) if metar.get("wgst") else None,
            visibility_m=vis_m,
            weather=metar.get("wxString"),
            clouds=clouds,
            temperature_c=int(metar.get("temp", 15)),
            dewpoint_c=int(metar.get("dewp", 10)),
            qnh_hpa=qnh,
            flight_category=flight_cat,
        )
    except MALFORMED_PAYLOAD_ERRORS:
        logger.exception("Malformed METAR payload for %s", icao_code)
        raise HTTPException(status_code=502, detail=f"Malformed METAR data for {icao_code.upper()}")


@router.get("/metar/{icao_code}/raw", tags=["METAR"])
async def get_metar_raw(icao_code: str):
    """Get raw METAR string"""
    try:
        data = await get_metar(icao_code, output_format="raw")
    except WeatherUpstreamError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    return {"icao_code": icao_code.upper(), "raw_metar": data.get("data", "")}


#  TAF
@router.get("/taf/{icao_code}", tags=["TAF"])
async def get_taf_data(icao_code: str):
    """Fetch TAF for an airport"""
    try:
        data = await get_taf(icao_code, output_format="json", include_metar=False)
    except WeatherUpstreamError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))

    if not data or len(data) == 0:
        raise HTTPException(status_code=404, detail=f"No TAF for {icao_code.upper()}")
    return {"icao_code": icao_code.upper(), "taf": data}


@router.get("/taf/{icao_code}/raw", tags=["TAF"])
async def get_taf_raw(icao_code: str):
    """Get raw TAF string"""
    try:
        data = await get_taf(icao_code, output_format="raw")
    except WeatherUpstreamError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    return {"icao_code": icao_code.upper(), "raw_taf": data.get("data", "")}


#  Helpers
def _determine_flight_category(ceiling_ft: Optional[int], visibility_m: int) -> str:
    """Determine flight category (VFR/MVFR/IFR/LIFR)"""
    visibility_sm = visibility_m / 1609.34

    if (ceiling_ft is not None and ceiling_ft < 500) or visibility_sm < 1:
        return "LIFR"
    if (ceiling_ft is not None and ceiling_ft < 1000) or visibility_sm < 3:
        return "IFR"
    if (ceiling_ft is not None and ceiling_ft < 3000) or visibility_sm < 5:
        return "MVFR"
    return "VFR"
