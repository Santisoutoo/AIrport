"""Async METAR/TAF fetcher backed by aviationweather.gov.

This module is imported from async FastAPI request handlers, so every network
call goes through a shared ``httpx.AsyncClient`` instead of the blocking
``requests`` library (which stalls the event loop for the whole process).

The client is created lazily and reused across requests; ``close_client()`` is
wired into the service lifespan so the connection pool is released on shutdown.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://aviationweather.gov/api/data"

#: Explicit timeout for every upstream call (connect/read/write/pool).
DEFAULT_TIMEOUT = httpx.Timeout(10.0)

_client: Optional[httpx.AsyncClient] = None


class WeatherUpstreamError(RuntimeError):
    """aviationweather.gov could not be used for this request.

    Covers transport failures, error statuses and undecodable payloads. The
    original ``httpx``/``ValueError`` exception is kept as ``__cause__``;
    ``status_code`` is the HTTP status the API layer should surface.
    """

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class NoWeatherDataError(ValueError):
    """The upstream is healthy but has no observation for this airport (404).

    Subclasses ``ValueError`` so existing callers that catch ``ValueError``
    keep working.
    """


def get_client() -> httpx.AsyncClient:
    """Return the shared ``AsyncClient``, creating it on first use."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
    return _client


async def close_client() -> None:
    """Close the shared client (called from the FastAPI lifespan shutdown)."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def _fetch(endpoint: str, params: Dict[str, Any], output_format: str) -> Dict[str, Any]:
    """GET ``endpoint`` on aviationweather.gov and decode the payload.

    Raises:
        WeatherUpstreamError: the upstream is unreachable, timed out, answered
            with an error status, or returned a body that is not valid JSON.
    """
    url = f"{BASE_URL}/{endpoint}"
    ids = params.get("ids")
    client = get_client()

    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        logger.warning("aviationweather %s timed out for %s: %s", endpoint, ids, exc)
        raise WeatherUpstreamError(f"Weather upstream timed out for {ids}", status_code=504) from exc
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "aviationweather %s returned HTTP %s for %s",
            endpoint,
            exc.response.status_code,
            ids,
        )
        raise WeatherUpstreamError(f"Weather upstream returned HTTP {exc.response.status_code} for {ids}") from exc
    except httpx.RequestError as exc:
        logger.warning("aviationweather %s unreachable for %s: %s", endpoint, ids, exc)
        raise WeatherUpstreamError(f"Weather upstream unreachable for {ids}") from exc

    if output_format != "json":
        return {"data": response.text}

    try:
        return response.json()
    except ValueError as exc:
        logger.warning("aviationweather %s returned a non-JSON payload for %s: %s", endpoint, ids, exc)
        raise WeatherUpstreamError(f"Weather upstream returned an undecodable payload for {ids}") from exc


async def get_metar(
    icao_code: str,
    output_format: str = "json",
    hours: Optional[int] = None,
) -> Dict[str, Any]:
    """Fetch the METAR for an airport given its ICAO code.

    Args:
        icao_code: ICAO airport code.
        output_format: raw, json, geojson, xml or iwxxm.
        hours: How many hours back to search.

    Returns:
        The decoded JSON payload, or ``{"data": <raw text>}`` for non-JSON formats.
    """
    params: Dict[str, Any] = {"ids": icao_code.upper(), "format": output_format}
    if hours:
        params["hours"] = hours

    return await _fetch("metar", params, output_format)


async def get_taf(
    icao_code: str,
    output_format: str = "json",
    include_metar: bool = True,
) -> Dict[str, Any]:
    """Fetch the TAF for an airport given its ICAO code.

    Args:
        icao_code: ICAO airport code.
        output_format: raw, json, geojson, xml or iwxxm.
        include_metar: Ask the upstream to bundle the current METAR.

    Returns:
        The decoded JSON payload, or ``{"data": <raw text>}`` for non-JSON formats.
    """
    params: Dict[str, Any] = {"ids": icao_code.upper(), "format": output_format}
    if include_metar:
        params["metar"] = "true"

    return await _fetch("taf", params, output_format)
