"""Local fixtures for the weather_service suite.

Self-contained on purpose: the root ``tests/conftest.py`` is shared with every
other suite and is not touched here.
"""

from __future__ import annotations

import pytest

from tests.weather.service_imports import metar_taf_fetcher


@pytest.fixture(autouse=True)
def _reset_shared_http_client():
    """Drop the module-level ``httpx.AsyncClient`` between tests.

    ``metar_taf_fetcher`` caches one client for the whole process; each test
    runs in its own event loop, so the cache must not survive a test.
    """
    metar_taf_fetcher._client = None
    yield
    metar_taf_fetcher._client = None


@pytest.fixture
def metar_payload() -> dict:
    """A nominal aviationweather.gov METAR record (LEST, wind 170/10, BKN 2500)."""
    return {
        "rawOb": "LEST 051200Z 17010KT 9999 BKN025 15/10 Q1013",
        "reportTime": "2026-08-05 12:00:00",
        "wdir": 170,
        "wspd": 10,
        "wgst": None,
        "visib": "6+",
        "wxString": None,
        "clouds": [{"cover": "BKN", "base": 2500}],
        "temp": 15,
        "dewp": 10,
        "altim": 1013.0,
    }
