import pytest
from core.runway_config import LEST_RWY_17, get_active_runway


def test_lest_17_constants():
    rw = LEST_RWY_17
    assert rw.icao == "LEST"
    assert rw.runway_id == "17"
    assert rw.vacate_exit_name == "E3"
    # Sanity: threshold must be in Galicia
    assert 42.5 < rw.threshold_lat < 43.5
    assert -9.0 < rw.threshold_lon < -8.0
    # Heading roughly southwards (170° magnetic)
    assert 160 <= rw.heading_deg <= 180


def test_get_active_runway_lest():
    assert get_active_runway("LEST") is LEST_RWY_17
    assert get_active_runway("lest") is LEST_RWY_17  # case-insensitive


def test_get_active_runway_unsupported():
    with pytest.raises(ValueError):
        get_active_runway("LEBL")
