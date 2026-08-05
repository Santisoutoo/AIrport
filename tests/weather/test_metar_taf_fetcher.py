"""Tests for ``services/weather_service/core/metar_taf_fetcher.py``.

Covers the httpx migration (issue #63): the fetcher must be async, must reuse a
single ``AsyncClient``, must always carry an explicit timeout, and must convert
upstream failures into ``WeatherUpstreamError`` with a sensible HTTP status
instead of letting raw transport errors escape into the API layer.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from tests.weather.service_imports import (
    WeatherUpstreamError,
    get_metar,
    get_taf,
    metar_taf_fetcher,
)

METAR_URL = "https://aviationweather.gov/api/data/metar"
TAF_URL = "https://aviationweather.gov/api/data/taf"


# ---------------------------------------------------------------------------
# Shared client
# ---------------------------------------------------------------------------


def test_get_client_reuses_a_single_instance():
    first = metar_taf_fetcher.get_client()
    second = metar_taf_fetcher.get_client()

    assert first is second
    assert isinstance(first, httpx.AsyncClient)


def test_client_has_an_explicit_timeout():
    client = metar_taf_fetcher.get_client()

    assert client.timeout.connect == 10.0
    assert client.timeout.read == 10.0


async def test_close_client_is_idempotent():
    client = metar_taf_fetcher.get_client()

    await metar_taf_fetcher.close_client()
    await metar_taf_fetcher.close_client()

    assert client.is_closed
    assert metar_taf_fetcher._client is None


async def test_get_client_replaces_a_closed_client():
    first = metar_taf_fetcher.get_client()
    await first.aclose()

    second = metar_taf_fetcher.get_client()

    assert second is not first
    assert not second.is_closed


# ---------------------------------------------------------------------------
# get_metar
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_metar_returns_decoded_json_and_uppercases_the_icao():
    route = respx.get(METAR_URL).mock(return_value=httpx.Response(200, json=[{"rawOb": "LEST 051200Z"}]))

    data = await get_metar("lest")

    assert data == [{"rawOb": "LEST 051200Z"}]
    request = route.calls[0].request
    assert dict(request.url.params) == {"ids": "LEST", "format": "json"}


@respx.mock
async def test_get_metar_forwards_the_hours_parameter():
    route = respx.get(METAR_URL).mock(return_value=httpx.Response(200, json=[]))

    await get_metar("LEST", hours=3)

    assert dict(route.calls[0].request.url.params) == {
        "ids": "LEST",
        "format": "json",
        "hours": "3",
    }


@respx.mock
async def test_get_metar_omits_hours_when_zero_or_none():
    route = respx.get(METAR_URL).mock(return_value=httpx.Response(200, json=[]))

    await get_metar("LEST", hours=0)

    assert "hours" not in dict(route.calls[0].request.url.params)


@respx.mock
async def test_get_metar_raw_format_returns_the_body_verbatim():
    respx.get(METAR_URL).mock(return_value=httpx.Response(200, text="LEST 051200Z 17010KT CAVOK 15/10 Q1013"))

    data = await get_metar("LEST", output_format="raw")

    assert data == {"data": "LEST 051200Z 17010KT CAVOK 15/10 Q1013"}


# ---------------------------------------------------------------------------
# get_taf
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_taf_requests_the_bundled_metar_by_default():
    route = respx.get(TAF_URL).mock(return_value=httpx.Response(200, json=[]))

    await get_taf("LEST")

    assert dict(route.calls[0].request.url.params) == {
        "ids": "LEST",
        "format": "json",
        "metar": "true",
    }


@respx.mock
async def test_get_taf_can_skip_the_bundled_metar():
    route = respx.get(TAF_URL).mock(return_value=httpx.Response(200, json=[]))

    await get_taf("LEST", include_metar=False)

    assert "metar" not in dict(route.calls[0].request.url.params)


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


@respx.mock
async def test_upstream_error_status_becomes_a_502():
    respx.get(METAR_URL).mock(return_value=httpx.Response(503))

    with pytest.raises(WeatherUpstreamError) as excinfo:
        await get_metar("LEST")

    assert excinfo.value.status_code == 502
    assert "503" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, httpx.HTTPStatusError)


@respx.mock
async def test_upstream_timeout_becomes_a_504():
    respx.get(METAR_URL).mock(side_effect=httpx.ConnectTimeout("too slow"))

    with pytest.raises(WeatherUpstreamError) as excinfo:
        await get_metar("LEST")

    assert excinfo.value.status_code == 504
    assert isinstance(excinfo.value.__cause__, httpx.TimeoutException)


@respx.mock
async def test_unreachable_upstream_becomes_a_502():
    respx.get(TAF_URL).mock(side_effect=httpx.ConnectError("no route to host"))

    with pytest.raises(WeatherUpstreamError) as excinfo:
        await get_taf("LEST")

    assert excinfo.value.status_code == 502
    assert isinstance(excinfo.value.__cause__, httpx.ConnectError)


@respx.mock
async def test_undecodable_json_becomes_a_502():
    respx.get(METAR_URL).mock(return_value=httpx.Response(200, text="<html>oops</html>"))

    with pytest.raises(WeatherUpstreamError) as excinfo:
        await get_metar("LEST")

    assert excinfo.value.status_code == 502
    assert "undecodable" in str(excinfo.value)


@respx.mock
async def test_upstream_failures_are_logged_with_context(caplog):
    respx.get(METAR_URL).mock(return_value=httpx.Response(500))

    with caplog.at_level("WARNING"), pytest.raises(WeatherUpstreamError):
        await get_metar("LEST")

    assert any("LEST" in record.getMessage() for record in caplog.records)


@respx.mock
async def test_raw_format_does_not_try_to_decode_json():
    """A raw request must not fail just because the body is not JSON."""
    respx.get(TAF_URL).mock(return_value=httpx.Response(200, text="TAF LEST 051100Z"))

    data = await get_taf("LEST", output_format="raw")

    assert data == {"data": "TAF LEST 051100Z"}
