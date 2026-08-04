"""Characterization tests for `ATISGenerator._parse_metar` (issue #49).

These pin down what the parser does *today*, quirks included, so the giant
functions around it can be broken up later without silently changing METAR
interpretation. Where current behaviour looks wrong (see the `Quirks` class)
the test asserts the wrong answer on purpose and says so — fixing it is a
separate change against a passing suite.

Payloads follow the shape aviationweather.gov returns for
`/api/data/metar?format=json`.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tests.weather._weather_service_import import atis_generator

ATISGenerator = atis_generator.ATISGenerator


def metar(**overrides) -> dict:
    """A well-formed LEBL payload, overridable field by field.

    `None` is a meaningful value for several fields, so removing a key is
    spelled by passing the sentinel `DROP`.
    """
    payload = {
        "icaoId": "LEBL",
        "reportTime": "2026-08-04 09:00:00",
        "rawOb": "LEBL 040900Z 18008KT 9999 FEW025 27/20 Q1015 NOSIG",
        "wdir": 180,
        "wspd": 8,
        "wgst": None,
        "visib": "6+",
        "wxString": None,
        "clouds": [{"cover": "FEW", "base": 2500}],
        "temp": 27,
        "dewp": 20,
        "altim": 1015,
    }
    payload.update(overrides)
    return {k: v for k, v in payload.items() if v is not DROP}


class _Drop:
    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "DROP"


DROP = _Drop()


@pytest.fixture
def parse():
    generator = ATISGenerator()
    return generator._parse_metar


# ---- Wind -------------------------------------------------------------------


def test_numeric_wind_direction_is_not_variable(parse):
    parsed = parse(metar(wdir=180, wspd=8))

    assert parsed["wind_direction"] == 180
    assert parsed["wind_speed"] == 8
    assert parsed["wind_variable"] is False


def test_string_wind_direction_is_coerced_to_int(parse):
    # aviationweather.gov returns wdir as a number, but the raw feed has been
    # seen serialising it as a string.
    assert parse(metar(wdir="240"))["wind_direction"] == 240


@pytest.mark.parametrize("wdir", ["VRB", None, DROP])
def test_variable_wind_reports_zero_degrees(parse, wdir):
    parsed = parse(metar(wdir=wdir))

    assert parsed["wind_direction"] == 0
    assert parsed["wind_variable"] is True


def test_gust_is_parsed_when_present(parse):
    assert parse(metar(wgst=25))["wind_gust"] == 25


@pytest.mark.parametrize("wgst", [None, DROP])
def test_absent_gust_is_none(parse, wgst):
    assert parse(metar(wgst=wgst))["wind_gust"] is None


def test_missing_wind_speed_defaults_to_calm(parse):
    assert parse(metar(wspd=DROP))["wind_speed"] == 0


# ---- Visibility -------------------------------------------------------------


def test_9999_in_raw_metar_wins_over_visib(parse):
    # The rawOb marker is checked first, so the statute-mile field is ignored.
    parsed = parse(metar(
        rawOb="LEBL 040900Z 18008KT 9999 FEW025 27/20 Q1015",
        visib="2",
    ))

    assert parsed["visibility_m"] == 9999


def test_statute_miles_are_converted_to_metres(parse):
    parsed = parse(metar(rawOb="LEBL 040900Z 18008KT 3SM BR 27/20 Q1015", visib="1.5"))

    assert parsed["visibility_m"] == int(1.5 * 1609.34)


def test_plus_suffix_is_stripped_before_conversion(parse):
    # "6+" means "6 statute miles or more"; 6 SM clamps below the 9999 ceiling.
    parsed = parse(metar(rawOb="LEBL 040900Z 18008KT 6SM FEW025 27/20 Q1015", visib="6+"))

    assert parsed["visibility_m"] == 9656


def test_long_visibility_is_clamped_to_9999(parse):
    parsed = parse(metar(rawOb="LEBL 040900Z 18008KT 10SM FEW025 27/20 Q1015", visib="10+"))

    assert parsed["visibility_m"] == 9999


def test_missing_visibility_falls_back_to_9999(parse):
    parsed = parse(metar(rawOb="LEBL 040900Z 18008KT FEW025 27/20 Q1015", visib=DROP))

    assert parsed["visibility_m"] == 9999


# ---- Weather phenomena ------------------------------------------------------


def test_known_phenomenon_is_described(parse):
    parsed = parse(metar(wxString="TSRA"))

    assert parsed["weather"] == "TSRA"
    assert parsed["weather_description"] == "thunderstorm with rain"


def test_unknown_phenomenon_passes_through_undescribed(parse):
    parsed = parse(metar(wxString="SG"))

    assert parsed["weather"] == "SG"
    assert parsed["weather_description"] == "SG"


@pytest.mark.parametrize("wx", [None, DROP])
def test_no_phenomenon_leaves_the_keys_unset(parse, wx):
    # Callers use parsed.get("weather"), so the keys are simply absent.
    parsed = parse(metar(wxString=wx))

    assert "weather" not in parsed
    assert "weather_description" not in parsed


# ---- Clouds and ceiling -----------------------------------------------------


def test_layers_are_preserved_in_order(parse):
    parsed = parse(metar(clouds=[
        {"cover": "FEW", "base": 1200},
        {"cover": "SCT", "base": 3000},
    ]))

    assert [(layer.coverage, layer.base_ft) for layer in parsed["clouds"]] == [
        ("FEW", 1200),
        ("SCT", 3000),
    ]


def test_ceiling_is_the_lowest_broken_or_overcast_layer(parse):
    parsed = parse(metar(clouds=[
        {"cover": "FEW", "base": 800},
        {"cover": "OVC", "base": 2500},
        {"cover": "BKN", "base": 1500},
    ]))

    assert parsed["ceiling_ft"] == 1500


def test_few_and_scattered_never_form_a_ceiling(parse):
    parsed = parse(metar(clouds=[
        {"cover": "FEW", "base": 700},
        {"cover": "SCT", "base": 1100},
    ]))

    assert parsed["ceiling_ft"] is None


@pytest.mark.parametrize("layer", [
    {"cover": "BKN", "base": None},
    {"cover": None, "base": 1500},
    {},
])
def test_incomplete_layers_are_skipped(parse, layer):
    parsed = parse(metar(clouds=[layer]))

    assert parsed["clouds"] == []
    assert parsed["ceiling_ft"] is None


def test_clear_sky_yields_no_layers(parse):
    parsed = parse(metar(clouds=[], rawOb="LEBL 040900Z 18008KT CAVOK 27/20 Q1015"))

    assert parsed["clouds"] == []
    assert parsed["ceiling_ft"] is None


# ---- Temperature and pressure -----------------------------------------------


def test_temperature_and_dewpoint_are_read(parse):
    parsed = parse(metar(temp=27, dewp=20))

    assert (parsed["temperature_c"], parsed["dewpoint_c"]) == (27, 20)


def test_subzero_temperatures_survive_truncation(parse):
    parsed = parse(metar(temp=-3.4, dewp=-5.6))

    # int() truncates toward zero rather than rounding.
    assert (parsed["temperature_c"], parsed["dewpoint_c"]) == (-3, -5)


def test_missing_temperature_falls_back_to_isa_ish_defaults(parse):
    parsed = parse(metar(temp=DROP, dewp=DROP))

    assert (parsed["temperature_c"], parsed["dewpoint_c"]) == (15, 10)


def test_qnh_is_read_in_hectopascals(parse):
    assert parse(metar(altim=1015))["qnh_hpa"] == 1015


def test_fractional_qnh_is_truncated(parse):
    assert parse(metar(altim=1015.9))["qnh_hpa"] == 1015


@pytest.mark.parametrize("altim", [None, DROP])
def test_missing_qnh_falls_back_to_standard_pressure(parse, altim):
    assert parse(metar(altim=altim))["qnh_hpa"] == 1013


# ---- Observation time and raw text ------------------------------------------


def test_report_time_is_parsed(parse):
    parsed = parse(metar(reportTime="2026-08-04 09:00:00"))

    assert parsed["observation_time"] == datetime(2026, 8, 4, 9, 0, 0)


def test_trailing_z_becomes_a_utc_offset(parse):
    parsed = parse(metar(reportTime="2026-08-04T09:00:00Z"))

    assert parsed["observation_time"] == datetime(2026, 8, 4, 9, 0, tzinfo=timezone.utc)


def test_missing_report_time_falls_back_to_now(parse):
    before = datetime.utcnow()
    parsed = parse(metar(reportTime=DROP))

    assert before <= parsed["observation_time"] <= datetime.utcnow()
    # Naive, i.e. not comparable with the tz-aware value the "Z" form produces.
    assert parsed["observation_time"].tzinfo is None


def test_raw_metar_is_carried_through(parse):
    raw = "LEBL 040900Z 18008KT 9999 FEW025 27/20 Q1015 NOSIG"

    assert parse(metar(rawOb=raw))["raw_metar"] == raw


def test_missing_raw_metar_becomes_empty_string(parse):
    assert parse(metar(rawOb=DROP))["raw_metar"] == ""


# ---- Real payloads ----------------------------------------------------------


def test_lemd_thunderstorm_payload(parse):
    parsed = parse({
        "icaoId": "LEMD",
        "reportTime": "2026-08-04 16:30:00",
        "rawOb": "LEMD 041630Z 22015G28KT 4000 TSRA BKN012CB OVC030 24/19 Q1008",
        "wdir": 220,
        "wspd": 15,
        "wgst": 28,
        "visib": "2.5",
        "wxString": "TSRA",
        "clouds": [{"cover": "BKN", "base": 1200}, {"cover": "OVC", "base": 3000}],
        "temp": 24,
        "dewp": 19,
        "altim": 1008,
    })

    assert parsed["wind_direction"] == 220
    assert parsed["wind_gust"] == 28
    assert parsed["visibility_m"] == 4023
    assert parsed["weather_description"] == "thunderstorm with rain"
    assert parsed["ceiling_ft"] == 1200
    assert parsed["qnh_hpa"] == 1008


def test_lest_low_visibility_payload(parse):
    parsed = parse({
        "icaoId": "LEST",
        "reportTime": "2026-08-04 06:00:00",
        "rawOb": "LEST 040600Z VRB02KT 0500 FG VV002 11/11 Q1021",
        "wdir": "VRB",
        "wspd": 2,
        "wgst": None,
        "visib": "0.3",
        "wxString": "FG",
        "clouds": [],
        "temp": 11,
        "dewp": 11,
        "altim": 1021,
    })

    assert parsed["wind_variable"] is True
    assert parsed["wind_direction"] == 0
    assert parsed["visibility_m"] == 482
    assert parsed["weather_description"] == "fog"
    assert parsed["ceiling_ft"] is None


# ---- Quirks -----------------------------------------------------------------


class TestQuirks:
    """Behaviour that is almost certainly wrong, pinned so a fix is deliberate.

    Each of these is a candidate bug report against `_parse_metar`; none is
    fixed here, because #49 is the safety net for the refactor, not the
    refactor.
    """

    def test_zero_visibility_reports_unlimited(self, parse):
        # `elif visib:` treats a numeric 0 as "field absent", so a METAR
        # reporting no visibility at all comes back as 9999 m — the exact
        # opposite of the truth.
        parsed = parse(metar(rawOb="LEST 040600Z VRB02KT 0000 FG 11/11 Q1021", visib=0))

        assert parsed["visibility_m"] == 9999

    def test_zero_gust_is_dropped(self, parse):
        # Harmless in practice (a 0 kt gust is not reported), but the same
        # falsy-vs-absent conflation as above.
        assert parse(metar(wgst=0))["wind_gust"] is None

    def test_9999_anywhere_in_the_raw_text_is_taken_as_visibility(self, parse):
        # The marker is matched against the whole rawOb, not the visibility
        # group, so an unrelated token wins.
        parsed = parse(metar(
            rawOb="LEBL 040900Z 18008KT 0500 FG RMK 9999 TEST 27/20 Q1015",
            visib="0.3",
        ))

        assert parsed["visibility_m"] == 9999
