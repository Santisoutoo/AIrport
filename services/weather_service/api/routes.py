from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from models.schemas import ATISResponse, ATISRequest, MetarResponse, HealthResponse, CloudLayer
from core.atis_generator import ATISGenerator
from core.metar_taf_fetcher import get_metar, get_taf
from core.database.connection import get_db, check_connection
from core.database.repositories.atis import ATISRepository

router = APIRouter()
generator = ATISGenerator()


#  Health
@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint"""
    db_ok = check_connection()
    return HealthResponse(
        status="healthy" if db_ok else "degraded",
        service="weather_service",
        version="1.0.0",
        db_connected=db_ok
    )


#  ATIS
@router.get("/atis/{icao_code}", response_model=ATISResponse, tags=["ATIS"])
async def generate_atis(
    icao_code: str,
    departure_runway: Optional[str] = Query(None, description="Departure runway"),
    arrival_runway: Optional[str] = Query(None, description="Arrival runway"),
    approach: Optional[str] = Query(None, description="Approach type"),
    db: Session = Depends(get_db)
):
    """Generate ATIS for an airport"""
    try:
        atis = generator.generate(
            icao_code=icao_code,
            departure_runway=departure_runway,
            arrival_runway=arrival_runway,
            approach=approach
        )
        repo = ATISRepository(db)
        repo.create(atis)
        return atis
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/atis/{icao_code}/latest", response_model=ATISResponse, tags=["ATIS"])
async def get_latest_atis(icao_code: str, db: Session = Depends(get_db)):
    """Get the most recent stored ATIS"""
    repo = ATISRepository(db)
    model = repo.get_latest_by_icao(icao_code)
    if not model:
        raise HTTPException(status_code=404, detail=f"No ATIS found for {icao_code.upper()}")
    return repo.to_response(model)


@router.get("/atis/{icao_code}/history", response_model=list[ATISResponse], tags=["ATIS"])
async def get_atis_history(
    icao_code: str,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
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
        data = get_metar(icao_code, output_format="json")
        if not data or len(data) == 0:
            raise HTTPException(status_code=404, detail=f"No METAR for {icao_code.upper()}")

        metar = data[0]

        # Wind
        wdir = metar.get("wdir")
        wind_dir = 0 if wdir == "VRB" or wdir is None else int(wdir)

        # Visibility
        visib = metar.get("visib")
        if visib == "10+":
            vis_m = 9999
        elif visib:
            vis_m = min(int(float(visib) * 1609.34), 9999)
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

        # Pressure
        altim = metar.get("altim")
        qnh = int(float(altim) * 33.8639) if altim else 1013

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
            flight_category=flight_cat
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metar/{icao_code}/raw", tags=["METAR"])
async def get_metar_raw(icao_code: str):
    """Get raw METAR string"""
    try:
        data = get_metar(icao_code, output_format="raw")
        return {"icao_code": icao_code.upper(), "raw_metar": data.get("data", "")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


#  TAF 
@router.get("/taf/{icao_code}", tags=["TAF"])
async def get_taf_data(icao_code: str):
    """Fetch TAF for an airport"""
    try:
        data = get_taf(icao_code, output_format="json", include_metar=False)
        if not data or len(data) == 0:
            raise HTTPException(status_code=404, detail=f"No TAF for {icao_code.upper()}")
        return {"icao_code": icao_code.upper(), "taf": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/taf/{icao_code}/raw", tags=["TAF"])
async def get_taf_raw(icao_code: str):
    """Get raw TAF string"""
    try:
        data = get_taf(icao_code, output_format="raw")
        return {"icao_code": icao_code.upper(), "raw_taf": data.get("data", "")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
