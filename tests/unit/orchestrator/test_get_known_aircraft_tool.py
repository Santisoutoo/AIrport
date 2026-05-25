"""Unit tests for agent/tools/aircraft.py::get_known_aircraft.

The function is a thin accessor over ``tool_context.state["known_aircraft"]``
-- populated upstream by ``runner._fetch_known_aircraft``. The tests below
guard the contract the LLM relies on.
"""

from __future__ import annotations

from types import SimpleNamespace

from agent.tools.aircraft import get_known_aircraft


def test_returns_state_known_aircraft():
    aircraft = [
        {"registration": "EC-MIG", "callsign": "IBE3421", "dependency": "DEL"},
        {"registration": "EC-NEW", "callsign": "VLG1234", "dependency": "APP"},
    ]
    ctx = SimpleNamespace(state={"known_aircraft": aircraft})

    result = get_known_aircraft(ctx)

    assert result == aircraft
    # Must return the same object (or an equivalent view), not silently rebuild it
    assert isinstance(result, list)


def test_returns_empty_list_when_state_missing():
    """Defensive: an agent invocation with no pre-fetch should yield []."""
    ctx = SimpleNamespace(state={})
    assert get_known_aircraft(ctx) == []


def test_returns_value_unchanged_when_state_has_list():
    """get_known_aircraft must return exactly what the runner placed in state.

    The runner is responsible for never injecting None -- the tool layer
    relies on it being either a list or absent.
    """
    aircraft = [{"registration": "EC-XX", "callsign": "FOO"}]
    ctx = SimpleNamespace(state={"known_aircraft": aircraft})
    assert get_known_aircraft(ctx) is aircraft
