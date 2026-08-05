"""Characterization tests for ``ATISGenerator._parse_metar`` (issues #63, #49).

``_parse_metar`` turns an aviationweather.gov JSON record into the dict that
feeds both the ATIS text and the ATIS response model. It is pure (no I/O), it
is the highest-fan-out helper of the weather service, and every fallback in it
is load-bearing for the broadcast. These tests pin down the behavior as it is
today so it can be refactored safely.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from tests.weather.service_imports import ATISGenerator, CloudLayer


@pytest.fixture
def generator() -> ATISGenerator:
    return ATISGenerator()


def parse(generator: ATISGenerator, **overrides) -> dict:
    """Parse a minimal METAR record, overriding individual upstream fields."""
    record = {
        "rawOb": "LEST 051200Z 17010KT BKN025 15/10 Q1013",
        "reportTime": "2026-08-05 12:00:00",
        "wdir": 170,
        "wspd": 10,
        "temp": 15,
        "dewp": 10,
        "altim": 1013.0,
    }
    record.update(overrides)
    return generator._parse_metar(record)


# ---------------------------------------------------------------------------
# Nominal record
# ---------------------------------------------------------------------------


def test_parses_a_nominal_record(generator, metar_payload):
    parsed = generator._parse_metar(metar_payload)

    assert parsed["raw_metar"] == metar_payload["rawOb"]
    assert parsed["observation_time"] == datetime(2026, 8, 5, 12, 0, 0)
    assert parsed["wind_direction"] == 170
    assert parsed["wind_variable"] is False
    assert parsed["wind_speed"] == 10
    assert parsed["wind_gust"] is None
    assert parsed["temperature_c"] == 15
    assert parsed["dewpoint_c"] == 10
    assert parsed["qnh_hpa"] == 1013


def test_report_time_zulu_suffix_is_converted_to_an_offset(generator):
    parsed = parse(generator, reportTime="2026-08-05T12:00:00Z")

    assert parsed["observation_time"].utcoffset().total_seconds() == 0


def test_absent_report_time_falls_back_to_now(generator):
    before = datetime.utcnow()

    parsed = generator._parse_metar({"rawOb": "", "wdir": 170, "wspd": 5})

    assert parsed["observation_time"] >= before


def test_null_report_time_is_not_handled(generator):
    """A ``null`` upstream ``reportTime`` is a hard failure, not a fallback.

    ``dict.get`` only substitutes the default when the key is *missing*, so an
    explicit ``None`` reaches ``.replace()``. The API layer maps the resulting
    ``AttributeError`` to a 502 (malformed upstream payload).
    """
    with pytest.raises(AttributeError):
        parse(generator, reportTime=None)


# ---------------------------------------------------------------------------
# Wind
# ---------------------------------------------------------------------------


def test_variable_wind_string_zeroes_the_direction(generator):
    parsed = parse(generator, wdir="VRB")

    assert parsed["wind_direction"] == 0
    assert parsed["wind_variable"] is True


def test_absent_wind_direction_is_treated_as_variable(generator):
    parsed = parse(generator, wdir=None)

    assert parsed["wind_direction"] == 0
    assert parsed["wind_variable"] is True


def test_wind_direction_is_coerced_to_int(generator):
    parsed = parse(generator, wdir="240")

    assert parsed["wind_direction"] == 240
    assert parsed["wind_variable"] is False


def test_missing_wind_speed_defaults_to_zero(generator):
    record = {
        "rawOb": "",
        "reportTime": "2026-08-05 12:00:00",
        "wdir": 170,
        "temp": 15,
        "dewp": 10,
    }

    parsed = generator._parse_metar(record)

    assert parsed["wind_speed"] == 0


def test_gusts_are_reported_when_present(generator):
    parsed = parse(generator, wgst="25")

    assert parsed["wind_gust"] == 25


def test_zero_gusts_are_reported_as_none(generator):
    """A falsy ``wgst`` is dropped rather than reported as 0 knots of gust."""
    parsed = parse(generator, wgst=0)

    assert parsed["wind_gust"] is None


# ---------------------------------------------------------------------------
# Visibility
# ---------------------------------------------------------------------------


def test_raw_9999_wins_over_the_numeric_visibility(generator):
    parsed = parse(generator, rawOb="LEST 051200Z 17010KT 9999 BKN025 15/10 Q1013", visib="3")

    assert parsed["visibility_m"] == 9999


def test_statute_miles_are_converted_to_metres(generator):
    parsed = parse(generator, visib="3")

    assert parsed["visibility_m"] == 4828  # int(3 * 1609.34)


def test_visibility_is_capped_at_9999_metres(generator):
    parsed = parse(generator, visib="10")

    assert parsed["visibility_m"] == 9999


def test_the_plus_suffix_is_stripped_before_converting(generator):
    parsed = parse(generator, visib="6+")

    assert parsed["visibility_m"] == 9656  # int(6 * 1609.34)


def test_missing_visibility_defaults_to_9999(generator):
    parsed = parse(generator, visib=None)

    assert parsed["visibility_m"] == 9999


# ---------------------------------------------------------------------------
# Weather phenomena
# ---------------------------------------------------------------------------


def test_known_weather_code_is_expanded(generator):
    parsed = parse(generator, wxString="TSRA")

    assert parsed["weather"] == "TSRA"
    assert parsed["weather_description"] == "thunderstorm with rain"


def test_unknown_weather_code_is_passed_through_verbatim(generator):
    parsed = parse(generator, wxString="FZDZ")

    assert parsed["weather"] == "FZDZ"
    assert parsed["weather_description"] == "FZDZ"


def test_absent_weather_leaves_both_keys_unset(generator):
    parsed = parse(generator, wxString=None)

    assert "weather" not in parsed
    assert "weather_description" not in parsed


# ---------------------------------------------------------------------------
# Clouds and ceiling
# ---------------------------------------------------------------------------


def test_cloud_layers_are_mapped_to_the_response_model(generator):
    parsed = parse(generator, clouds=[{"cover": "FEW", "base": 1200}])

    assert parsed["clouds"] == [CloudLayer(coverage="FEW", base_ft=1200)]


def test_ceiling_is_the_lowest_broken_or_overcast_layer(generator):
    parsed = parse(
        generator,
        clouds=[
            {"cover": "FEW", "base": 800},
            {"cover": "OVC", "base": 3000},
            {"cover": "BKN", "base": 1500},
        ],
    )

    assert parsed["ceiling_ft"] == 1500
    assert len(parsed["clouds"]) == 3


def test_few_and_scattered_layers_do_not_set_a_ceiling(generator):
    parsed = parse(
        generator,
        clouds=[{"cover": "FEW", "base": 900}, {"cover": "SCT", "base": 1200}],
    )

    assert parsed["ceiling_ft"] is None


def test_layers_without_a_base_are_dropped(generator):
    parsed = parse(
        generator,
        clouds=[{"cover": "BKN", "base": None}, {"cover": None, "base": 2000}],
    )

    assert parsed["clouds"] == []
    assert parsed["ceiling_ft"] is None


def test_no_clouds_key_yields_an_empty_layer_list(generator):
    parsed = parse(generator)

    assert parsed["clouds"] == []
    assert parsed["ceiling_ft"] is None


# ---------------------------------------------------------------------------
# Temperature and pressure
# ---------------------------------------------------------------------------


def test_missing_temperatures_fall_back_to_isa_ish_defaults(generator):
    record = {
        "rawOb": "",
        "reportTime": "2026-08-05 12:00:00",
        "wdir": 170,
        "wspd": 5,
    }

    parsed = generator._parse_metar(record)

    assert parsed["temperature_c"] == 15
    assert parsed["dewpoint_c"] == 10


def test_negative_temperatures_survive_the_int_coercion(generator):
    parsed = parse(generator, temp=-4, dewp=-9)

    assert parsed["temperature_c"] == -4
    assert parsed["dewpoint_c"] == -9


def test_altimeter_is_truncated_to_whole_hectopascals(generator):
    parsed = parse(generator, altim="1013.7")

    assert parsed["qnh_hpa"] == 1013


def test_missing_altimeter_defaults_to_standard_pressure(generator):
    parsed = parse(generator, altim=None)

    assert parsed["qnh_hpa"] == 1013
