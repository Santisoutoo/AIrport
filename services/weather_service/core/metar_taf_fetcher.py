import requests
from typing import Optional, Dict, Any


def get_metar(
    icao_code: str,
    output_format: str = "json",
    hours: Optional[int] = None
) -> Dict[str, Any]:
    """
    Obtiene el METAR para un aeropuerto dado su código ICAO.

    Args:
        icao_code: Código ICAO del aeropuerto
        output_format: raw, json, geojson, xml, iwxxm
        hours: Número de horas hacia atrás para buscar

    Returns:
        Dict con los datos del METAR en formato JSON
    """
    url = 'https://aviationweather.gov/api/data/metar'

    params = {
        "ids": icao_code.upper(),
        "format": output_format
    }

    if hours:
        params["hours"] = hours

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    if output_format == "json":
        return response.json()
    else:
        return {"data": response.text}


def get_taf(
    icao_code: str,
    output_format: str = "json",
    include_metar: bool = True
) -> Dict[str, Any]:
    """
    Obtiene TAF para un aeropuerto dado su código ICAO.

    Args:
        icao_code: Código ICAO del aeropuerto
        output_format: raw, json, geojson, xml, iwxxm
        include_metar: bool

    Returns:
        Dict con los datos del TAF en formato JSON
    """
    url = 'https://aviationweather.gov/api/data/taf'

    params = {
        "ids": icao_code.upper(),
        "format": output_format
    }

    if include_metar:
        params["metar"] = "true"

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    if output_format == "json":
        return response.json()
    else:
        return {"data": response.text}
