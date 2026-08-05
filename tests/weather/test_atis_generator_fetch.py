"""Tests for the async METAR fetch path of ``ATISGenerator`` (issue #63).

``generate`` and ``_fetch_metar`` became coroutines when the fetcher moved from
``requests`` to ``httpx``. These tests pin the end-to-end behavior and, most
importantly, that an upstream outage is no longer flattened into a
``ValueError`` (which the API layer used to report as a 404 "airport not
found").
"""

from __future__ import annotations

import httpx
import pytest
import respx

from tests.weather.service_imports import (
    ATISGenerator,
    NoWeatherDataError,
    WeatherUpstreamError,
)

METAR_URL = "https://aviationweather.gov/api/data/metar"


@pytest.fixture
def generator() -> ATISGenerator:
    return ATISGenerator()


# ---------------------------------------------------------------------------
# _fetch_metar
# ---------------------------------------------------------------------------


@respx.mock
async def test_fetch_metar_returns_the_first_observation(generator, metar_payload):
    respx.get(METAR_URL).mock(return_value=httpx.Response(200, json=[metar_payload, {"rawOb": "second"}]))

    data = await generator._fetch_metar("LEST")

    assert data == metar_payload


@respx.mock
async def test_fetch_metar_raises_no_weather_data_on_an_empty_list(generator):
    respx.get(METAR_URL).mock(return_value=httpx.Response(200, json=[]))

    with pytest.raises(NoWeatherDataError, match="No METAR data available for LEST"):
        await generator._fetch_metar("LEST")


@respx.mock
async def test_upstream_outage_is_not_disguised_as_missing_data(generator):
    """Regression for #63: a 500 upstream must not become a 404 "unknown airport"."""
    respx.get(METAR_URL).mock(return_value=httpx.Response(500))

    with pytest.raises(WeatherUpstreamError) as excinfo:
        await generator._fetch_metar("LEST")

    assert not isinstance(excinfo.value, ValueError)
    assert excinfo.value.status_code == 502


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


@respx.mock
async def test_generate_builds_a_full_atis_response(generator, metar_payload):
    respx.get(METAR_URL).mock(return_value=httpx.Response(200, json=[metar_payload]))

    atis = await generator.generate("LEST", departure_runway="17", arrival_runway="17")

    assert atis.icao_code == "LEST"
    assert atis.atis_letter == "A"
    assert atis.wind_direction == 170
    assert atis.qnh_hpa == 1013
    assert atis.transition_level == "FL75"  # QNH 1013 falls in the 996-1013 band
    assert atis.departure_runway == "17"
    assert atis.arrival_runway == "17"
    assert "Santiago information ALFA." in atis.atis_text
    assert "Wind 170 degrees, 10 knots." in atis.atis_text


@respx.mock
async def test_generate_auto_selects_the_runway_from_the_wind(generator, metar_payload):
    respx.get(METAR_URL).mock(return_value=httpx.Response(200, json=[metar_payload]))

    atis = await generator.generate("LEST")

    # LEST has 17/35; wind 170 favours runway 17.
    assert atis.arrival_runway == "17"
    assert atis.departure_runway == "17"
    assert atis.approach_type == "ILS"


@respx.mock
async def test_preview_mode_does_not_advance_the_atis_letter(generator, metar_payload):
    respx.get(METAR_URL).mock(return_value=httpx.Response(200, json=[metar_payload]))

    first = await generator.generate("LEST", preview=True)
    second = await generator.generate("LEST", preview=True)

    assert first.atis_letter == second.atis_letter == "A"


@respx.mock
async def test_the_atis_letter_advances_between_broadcasts(generator, metar_payload):
    respx.get(METAR_URL).mock(return_value=httpx.Response(200, json=[metar_payload]))

    first = await generator.generate("LEST")
    second = await generator.generate("LEST")

    assert (first.atis_letter, second.atis_letter) == ("A", "B")


@respx.mock
async def test_unknown_airports_fall_back_to_default_airport_data(generator, metar_payload):
    respx.get(METAR_URL).mock(return_value=httpx.Response(200, json=[metar_payload]))

    atis = await generator.generate("ZZZZ")

    assert atis.transition_altitude == 6000
    assert atis.arrival_runway in {"09", "27"}
    assert "ZZZZ information ALFA." in atis.atis_text


@respx.mock
async def test_remarks_and_qfe_are_appended_to_the_broadcast(generator, metar_payload):
    respx.get(METAR_URL).mock(return_value=httpx.Response(200, json=[metar_payload]))

    atis = await generator.generate("LEST", qfe=990, remarks="birds reported")

    assert "QFE 990 hectopascals." in atis.atis_text
    assert atis.atis_text.endswith("RMK birds reported")


@respx.mock
async def test_transition_level_and_altitude_can_be_suppressed(generator, metar_payload):
    respx.get(METAR_URL).mock(return_value=httpx.Response(200, json=[metar_payload]))

    atis = await generator.generate("LEST", include_tl=False, include_ta=False)

    assert "Transition level" not in atis.atis_text
    assert "Transition altitude" not in atis.atis_text
    # Still reported in the structured response.
    assert atis.transition_level == "FL75"
