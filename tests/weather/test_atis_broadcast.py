"""Characterization tests for the rest of `ATISGenerator` (issue #49).

`_parse_metar` is covered in `test_atis_generator.py`; this file pins the
methods around it — runway and approach selection, the ATIS letter sequence,
transition levels, and the broadcast text that `generate()` assembles from all
of them. Together they are the safety net for breaking the class up later.

No network: `get_metar` is replaced at the module level, so `_fetch_metar` runs
its real code against a canned payload.
"""

from __future__ import annotations

import pytest

from tests.weather._weather_service_import import atis_generator

ATISGenerator = atis_generator.ATISGenerator

LEBL_METAR = {
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


@pytest.fixture
def generator(monkeypatch):
    """An ATISGenerator whose METAR feed returns LEBL_METAR."""
    monkeypatch.setattr(atis_generator, "get_metar", lambda icao, output_format="json": [LEBL_METAR])
    return ATISGenerator()


# ---- Fetching ---------------------------------------------------------------


def test_fetch_returns_the_first_observation(generator):
    assert generator._fetch_metar("LEBL") == LEBL_METAR


def test_empty_feed_is_reported_as_a_fetch_failure(monkeypatch):
    monkeypatch.setattr(atis_generator, "get_metar", lambda icao, output_format="json": [])

    with pytest.raises(ValueError, match="Failed to fetch METAR for LEBL"):
        ATISGenerator()._fetch_metar("LEBL")


def test_feed_errors_are_wrapped(monkeypatch):
    def boom(icao, output_format="json"):
        raise ConnectionError("upstream down")

    monkeypatch.setattr(atis_generator, "get_metar", boom)

    with pytest.raises(ValueError, match="upstream down"):
        ATISGenerator()._fetch_metar("LEBL")


# ---- Runway selection -------------------------------------------------------


@pytest.mark.parametrize("wind, expected", [
    (200, "20"),    # exact alignment with 20
    (180, "20"),    # nearest of 02/20/07/25
    (70, "07L"),    # ties break on the first runway listed
    (250, "25L"),
    (20, "02"),
])
def test_runway_is_the_closest_heading_to_the_wind(wind, expected):
    runways = ["02", "20", "07L", "07R", "25L", "25R"]

    assert ATISGenerator()._select_runway_from_wind(wind, runways) == expected


def test_side_suffixes_are_stripped_before_comparing(generator):
    assert generator._select_runway_from_wind(140, ["14L", "32R"]) == "14L"


def test_non_numeric_runways_are_skipped(generator):
    assert generator._select_runway_from_wind(180, ["ABC", "18"]) == "18"


def test_no_usable_runway_yields_none(generator):
    assert generator._select_runway_from_wind(180, ["ABC"]) is None
    assert generator._select_runway_from_wind(180, []) is None


# ---- Approach selection -----------------------------------------------------


@pytest.mark.parametrize("available, expected", [
    (["ILS", "VOR", "RNAV"], "ILS"),
    (["VOR", "RNAV"], "VOR"),
    (["RNAV"], "RNAV"),
])
def test_approach_preference_is_ils_then_vor_then_rnav(generator, available, expected):
    airport = {"approaches": {"25R": available}}

    assert generator._select_approach_for_runway("25R", airport) == expected


def test_unranked_approach_falls_back_to_the_first_listed(generator):
    airport = {"approaches": {"25R": ["LOC", "NDB"]}}

    assert generator._select_approach_for_runway("25R", airport) == "LOC"


@pytest.mark.parametrize("airport", [{"approaches": {"25R": []}}, {"approaches": {}}, {}])
def test_runway_without_approaches_yields_none(generator, airport):
    assert generator._select_approach_for_runway("25R", airport) is None


# ---- ATIS letter sequence ---------------------------------------------------


def test_letters_advance_per_airport(generator):
    assert generator._get_next_atis_letter("LEBL") == "A"
    assert generator._get_next_atis_letter("LEBL") == "B"
    assert generator._get_next_atis_letter("LEMD") == "A"
    assert generator._get_next_atis_letter("LEBL") == "C"


def test_preview_does_not_consume_a_letter(generator):
    assert generator._get_next_atis_letter("LEBL") == "A"
    assert generator._get_next_atis_letter("LEBL", preview=True) == "B"
    assert generator._get_next_atis_letter("LEBL", preview=True) == "B"
    assert generator._get_next_atis_letter("LEBL") == "B"


def test_the_sequence_wraps_after_z(generator):
    generator._atis_counters["LEBL"] = 25

    assert generator._get_next_atis_letter("LEBL") == "A"


# ---- Transition level -------------------------------------------------------


@pytest.mark.parametrize("qnh, expected", [
    (1040, "FL65"), (1032, "FL65"),
    (1031, "FL70"), (1014, "FL70"),
    (1013, "FL75"), (996, "FL75"),
    (995, "FL80"), (978, "FL80"),
    (977, "FL90"), (950, "FL90"),
])
def test_transition_level_boundaries(generator, qnh, expected):
    assert generator._calculate_transition_level(qnh) == expected


# ---- Unknown airports -------------------------------------------------------


def test_unknown_airport_gets_a_generic_09_27_layout(generator):
    default = generator._get_default_airport("LEXX")

    assert default["name"] == "LEXX"
    assert default["runways"] == ["09", "27"]
    assert default["approaches"] == {"09": ["RNAV"], "27": ["RNAV"]}


def test_generate_falls_back_to_the_default_layout(generator):
    response = generator.generate("LEXX")

    assert response.arrival_runway in {"09", "27"}
    assert response.approach_type == "RNAV"
    assert response.transition_altitude == 6000


# ---- generate() -------------------------------------------------------------


def test_generate_auto_selects_runways_from_the_wind(generator):
    response = generator.generate("LEBL")

    assert response.icao_code == "LEBL"
    assert response.atis_letter == "A"
    assert response.departure_runway == "20"
    assert response.arrival_runway == "20"
    assert response.qnh_hpa == 1015
    assert response.transition_level == "FL70"
    assert response.raw_metar == LEBL_METAR["rawOb"]


def test_atc_values_override_auto_selection(generator):
    response = generator.generate(
        "LEBL", departure_runway="25L", arrival_runway="25R", approach="ILS"
    )

    assert (response.departure_runway, response.arrival_runway) == ("25L", "25R")
    assert response.approach_type == "ILS"


def test_icao_code_is_upcased(generator):
    assert generator.generate("lebl").icao_code == "LEBL"


def test_variable_wind_leaves_runway_selection_to_atc(monkeypatch):
    calm = dict(LEBL_METAR, wdir="VRB", wspd=3)
    monkeypatch.setattr(atis_generator, "get_metar", lambda icao, output_format="json": [calm])

    response = ATISGenerator().generate("LEBL")

    assert response.wind_variable is True
    assert response.departure_runway is None
    assert response.arrival_runway is None
    assert "Wind variable at 3 knots." in response.atis_text


# ---- Broadcast text ---------------------------------------------------------


def test_broadcast_reads_out_the_full_picture(generator):
    text = generator.generate("LEBL").atis_text

    assert text.startswith("Barcelona El Prat information ALFA.")
    assert "Departure runway 20." in text
    assert "Arrival runway 20." in text
    assert "Wind 180 degrees, 8 knots." in text
    assert "Visibility 10.0 kilometers." in text
    assert "Clouds few at 2500 feet." in text
    assert "Temperature 27, dewpoint 20." in text
    assert "QNH 1015 hectopascals." in text
    assert "Transition level FL70." in text
    assert "Transition altitude 6000 feet." in text
    assert "Information ALFA recorded at 0900 Zulu." in text
    assert text.endswith("Advise on initial contact you have information ALFA.")


def test_gusts_and_weather_reach_the_broadcast(monkeypatch):
    stormy = dict(
        LEBL_METAR,
        wdir=220, wspd=15, wgst=28, wxString="TSRA",
        clouds=[{"cover": "BKN", "base": 1200}, {"cover": "OVC", "base": 3000}],
    )
    monkeypatch.setattr(atis_generator, "get_metar", lambda icao, output_format="json": [stormy])

    text = ATISGenerator().generate("LEBL").atis_text

    assert "Wind 220 degrees, 15 knots, gusting 28." in text
    assert "Weather: thunderstorm with rain." in text
    assert "Clouds broken at 1200 feet, overcast at 3000 feet." in text


def test_optional_sections_are_suppressed_on_request(generator):
    text = generator.generate("LEBL", include_tl=False, include_ta=False).atis_text

    assert "Transition level" not in text
    assert "Transition altitude" not in text


def test_qfe_and_remarks_are_appended(generator):
    text = generator.generate("LEBL", qfe=1013, remarks="  bird activity  ").atis_text

    assert "QFE 1013 hectopascals." in text
    assert text.endswith("RMK bird activity")


def test_blank_remarks_are_dropped(generator):
    assert "RMK" not in generator.generate("LEBL", remarks="   ").atis_text


def test_preview_broadcasts_do_not_burn_a_letter(generator):
    assert generator.generate("LEBL", preview=True).atis_letter == "A"
    assert generator.generate("LEBL").atis_letter == "A"
    assert generator.generate("LEBL").atis_letter == "B"


class TestBroadcastQuirks:
    """Pinned oddities in the spoken text — see `TestQuirks` in the sibling file."""

    def test_a_northerly_wind_is_announced_as_variable(self, monkeypatch):
        # `parsed["wind_direction"] == 0` is treated as "variable", but 0 is
        # also what a wind from 360 degrees parses to, so a real northerly
        # loses its direction in the broadcast.
        northerly = dict(LEBL_METAR, wdir=0, wspd=12)
        monkeypatch.setattr(
            atis_generator, "get_metar", lambda icao, output_format="json": [northerly]
        )

        response = ATISGenerator().generate("LEBL")

        assert response.wind_variable is False
        assert "Wind variable at 12 knots." in response.atis_text

    def test_cavok_is_unreachable_through_generate(self, generator):
        # `_generate_atis_text` has a CAVOK branch, but `_parse_metar` never
        # sets the `cavok` key, so a CAVOK observation is still read out as a
        # visibility figure. The branch is only reachable by calling the text
        # builder directly.
        parsed = generator._parse_metar({
            "rawOb": "LEBL 040900Z 18008KT CAVOK 27/20 Q1015",
            "reportTime": "2026-08-04 09:00:00",
            "wdir": 180, "wspd": 8, "temp": 27, "dewp": 20, "altim": 1015,
        })
        assert "cavok" not in parsed

        spoken = generator._generate_atis_text(
            icao_code="LEBL",
            atis_letter="A",
            parsed={**parsed, "cavok": True},
            departure_runway=None,
            arrival_runway=None,
            approach=None,
            transition_level="FL70",
            transition_altitude=6000,
            airport_name="Barcelona El Prat",
        )

        assert "CAVOK." in spoken
        assert "Visibility" not in spoken

    def test_visibility_is_announced_to_one_decimal_kilometre(self, generator):
        # 9999 m is the METAR code for "10 km or more"; rounding prints it as
        # a flat 10.0 km, which is the intent, but 9500 m reads as 9.5 km.
        assert "Visibility 10.0 kilometers." in generator.generate("LEBL").atis_text
