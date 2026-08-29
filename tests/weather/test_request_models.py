"""Contract tests for the grouped ATIS request model (issue #64).

`generate_atis` used to take nine flat parameters; they now live in
`models.schemas.ATISOptions`. The HTTP contract must be untouched, so these
tests lock the query-parameter names, defaults and descriptions that the
OpenAPI schema exposes to the HMI proxy and the other clients.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from tests.weather.service_imports import routes, schemas

PREFIX = "/api/v1/weather"

EXPECTED_QUERY_PARAMS = {
    "departure_runway": ("Departure runway", None),
    "arrival_runway": ("Arrival runway", None),
    "approach": ("Approach type", None),
    "qfe": ("QFE in hPa (set by ATC)", None),
    "include_tl": ("Include Transition Level in ATIS", True),
    "include_ta": ("Include Transition Altitude in ATIS", True),
    "remarks": ("ATC remarks (appended as RMK)", None),
    "preview": ("Preview mode: no DB save, letter not incremented", False),
}


@pytest.fixture(scope="module")
def atis_operation() -> dict:
    app = FastAPI()
    app.include_router(routes.router, prefix=PREFIX)
    return app.openapi()["paths"][f"{PREFIX}/atis/{{icao_code}}"]["get"]


def test_the_endpoint_still_exposes_every_query_parameter(atis_operation):
    names = {p["name"] for p in atis_operation["parameters"] if p["in"] == "query"}

    assert names == set(EXPECTED_QUERY_PARAMS)


@pytest.mark.parametrize("name", sorted(EXPECTED_QUERY_PARAMS))
def test_query_parameter_metadata_is_preserved(atis_operation, name):
    param = next(p for p in atis_operation["parameters"] if p["name"] == name)
    description, default = EXPECTED_QUERY_PARAMS[name]

    assert param["in"] == "query"
    assert param["required"] is False
    assert param["description"] == description
    assert param["schema"].get("default") == default


def test_icao_code_stays_a_path_parameter(atis_operation):
    icao = next(p for p in atis_operation["parameters"] if p["name"] == "icao_code")

    assert icao["in"] == "path"
    assert icao["required"] is True


# ---------------------------------------------------------------------------
# The model itself
# ---------------------------------------------------------------------------


def test_defaults_match_the_previous_signature():
    options = schemas.ATISOptions()

    assert options.model_dump() == {
        "departure_runway": None,
        "arrival_runway": None,
        "approach": None,
        "qfe": None,
        "include_tl": True,
        "include_ta": True,
        "remarks": None,
        "preview": False,
    }


def test_as_query_collects_the_parameters():
    options = schemas.ATISOptions.as_query(
        departure_runway="17",
        arrival_runway="35",
        approach="ILS",
        qfe=990,
        include_tl=False,
        include_ta=False,
        remarks="birds",
        preview=True,
    )

    assert options.departure_runway == "17"
    assert options.arrival_runway == "35"
    assert options.approach == "ILS"
    assert options.qfe == 990
    assert options.include_tl is False
    assert options.include_ta is False
    assert options.remarks == "birds"
    assert options.preview is True


def test_model_dump_matches_the_generator_keyword_arguments():
    """``generate_atis`` splats the model into ``ATISGenerator.generate``."""
    import inspect

    generate_params = set(inspect.signature(routes.generator.generate).parameters)

    assert set(schemas.ATISOptions().model_dump()) | {"icao_code"} == generate_params
