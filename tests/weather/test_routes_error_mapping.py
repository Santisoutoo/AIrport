"""HTTP-contract tests for ``services/weather_service/api/routes.py`` (issue #63).

The endpoints used to funnel every failure through ``except Exception`` and
answer ``500 <str(exc)>``, which made an upstream outage indistinguishable from
a bug in this service. These tests pin the narrowed mapping:

* no observation for the airport -> 404
* aviationweather.gov unreachable / error status -> 502
* aviationweather.gov timeout -> 504
* payload we cannot parse -> 502
* database write failure -> 500 with a generic message

They also pin the field names of the successful responses, so the request-model
refactor in #64 cannot silently change the contract.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from tests.weather.service_imports import routes

METAR_URL = "https://aviationweather.gov/api/data/metar"
TAF_URL = "https://aviationweather.gov/api/data/taf"
PREFIX = "/api/v1/weather"


class _FakeRepository:
    """Stand-in for ATISRepository: records what would have been persisted."""

    created: list = []

    def __init__(self, db):
        self.db = db

    def create(self, atis):
        type(self).created.append(atis)
        return atis


@pytest.fixture
def client(monkeypatch):
    _FakeRepository.created = []
    monkeypatch.setattr(routes, "ATISRepository", _FakeRepository)
    # Fresh generator per test so the ATIS letter sequence is deterministic.
    monkeypatch.setattr(routes, "generator", routes.ATISGenerator())

    app = FastAPI()
    app.include_router(routes.router, prefix=PREFIX)
    app.dependency_overrides[routes.get_db] = lambda: None

    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Happy paths (contract baseline for #64)
# ---------------------------------------------------------------------------


@respx.mock
def test_generate_atis_returns_the_broadcast_and_persists_it(client, metar_payload):
    respx.get(METAR_URL).mock(return_value=httpx.Response(200, json=[metar_payload]))

    response = client.get(
        f"{PREFIX}/atis/LEST",
        params={"departure_runway": "17", "arrival_runway": "17", "approach": "ILS"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["icao_code"] == "LEST"
    assert body["atis_letter"] == "A"
    assert body["departure_runway"] == "17"
    assert body["approach_type"] == "ILS"
    assert "Santiago information ALFA." in body["atis_text"]
    assert len(_FakeRepository.created) == 1


@respx.mock
def test_preview_mode_skips_persistence(client, metar_payload):
    respx.get(METAR_URL).mock(return_value=httpx.Response(200, json=[metar_payload]))

    response = client.get(f"{PREFIX}/atis/LEST", params={"preview": "true"})

    assert response.status_code == 200
    assert _FakeRepository.created == []


@respx.mock
def test_metar_endpoint_shapes_the_upstream_record(client, metar_payload):
    respx.get(METAR_URL).mock(return_value=httpx.Response(200, json=[metar_payload]))

    response = client.get(f"{PREFIX}/metar/LEST")

    assert response.status_code == 200
    body = response.json()
    assert body["icao_code"] == "LEST"
    assert body["wind_direction"] == 170
    assert body["visibility_m"] == 9999
    assert body["qnh_hpa"] == 1013
    # BKN at 2500 ft is a ceiling below 3000 ft -> marginal VFR.
    assert body["flight_category"] == "MVFR"


@respx.mock
def test_raw_metar_endpoint_returns_the_body_verbatim(client):
    respx.get(METAR_URL).mock(return_value=httpx.Response(200, text="LEST 051200Z CAVOK"))

    response = client.get(f"{PREFIX}/metar/lest/raw")

    assert response.status_code == 200
    assert response.json() == {"icao_code": "LEST", "raw_metar": "LEST 051200Z CAVOK"}


@respx.mock
def test_taf_endpoint_wraps_the_upstream_list(client):
    respx.get(TAF_URL).mock(return_value=httpx.Response(200, json=[{"rawTAF": "TAF LEST"}]))

    response = client.get(f"{PREFIX}/taf/LEST")

    assert response.status_code == 200
    assert response.json() == {"icao_code": "LEST", "taf": [{"rawTAF": "TAF LEST"}]}


@respx.mock
def test_raw_taf_endpoint_returns_the_body_verbatim(client):
    respx.get(TAF_URL).mock(return_value=httpx.Response(200, text="TAF LEST 051100Z"))

    response = client.get(f"{PREFIX}/taf/LEST/raw")

    assert response.status_code == 200
    assert response.json() == {"icao_code": "LEST", "raw_taf": "TAF LEST 051100Z"}


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


@respx.mock
def test_no_observation_is_a_404(client):
    respx.get(METAR_URL).mock(return_value=httpx.Response(200, json=[]))

    response = client.get(f"{PREFIX}/atis/LEST")

    assert response.status_code == 404
    assert "No METAR data available" in response.json()["detail"]


@respx.mock
@pytest.mark.parametrize(
    "path",
    ["/atis/LEST", "/metar/LEST", "/metar/LEST/raw", "/taf/LEST", "/taf/LEST/raw"],
)
def test_upstream_outage_is_a_502_everywhere(client, path):
    respx.get(METAR_URL).mock(return_value=httpx.Response(503))
    respx.get(TAF_URL).mock(return_value=httpx.Response(503))

    response = client.get(f"{PREFIX}{path}")

    assert response.status_code == 502
    assert "LEST" in response.json()["detail"]


@respx.mock
def test_upstream_timeout_is_a_504(client):
    respx.get(METAR_URL).mock(side_effect=httpx.ReadTimeout("too slow"))

    response = client.get(f"{PREFIX}/atis/LEST")

    assert response.status_code == 504


@respx.mock
def test_malformed_upstream_payload_is_a_502_not_a_500(client):
    """A ``null`` reportTime blows up inside the parser; the client sees 502."""
    respx.get(METAR_URL).mock(
        return_value=httpx.Response(200, json=[{"rawOb": "LEST", "reportTime": None}])
    )

    response = client.get(f"{PREFIX}/atis/LEST")

    assert response.status_code == 502
    assert response.json()["detail"] == "Malformed METAR data for LEST"


@respx.mock
def test_malformed_payload_on_the_metar_endpoint_is_a_502(client):
    respx.get(METAR_URL).mock(
        return_value=httpx.Response(200, json=[{"rawOb": "LEST", "wdir": "north"}])
    )

    response = client.get(f"{PREFIX}/metar/LEST")

    assert response.status_code == 502
    assert response.json()["detail"] == "Malformed METAR data for LEST"


@respx.mock
def test_database_failure_is_a_500_without_leaking_the_driver_error(
    client, monkeypatch, metar_payload
):
    respx.get(METAR_URL).mock(return_value=httpx.Response(200, json=[metar_payload]))

    class _BrokenRepository(_FakeRepository):
        def create(self, atis):
            raise OperationalError("INSERT", {}, Exception("connection refused"))

    monkeypatch.setattr(routes, "ATISRepository", _BrokenRepository)

    response = client.get(f"{PREFIX}/atis/LEST")

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to store the generated ATIS"
    assert "connection refused" not in response.text


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health_reports_degraded_when_the_database_is_down(client, monkeypatch):
    monkeypatch.setattr(routes, "check_connection", lambda: False)

    response = client.get(f"{PREFIX}/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["service"] == "weather_service"
    assert body["db_connected"] is False
