"""Unit tests for the three frequency-change "advance" tools:

  - advance_to_gnd          (DEL  → GND, departure)
  - advance_to_twr          (GND  → TWR, departure)
  - advance_to_gnd_arrival  (TWR  → GND, arrival reverse handoff)

All three follow the same shape: read ``known_aircraft`` from
``tool_context.state``, lookup the callsign by registration, emit a readback
like ``"121.9, IBE3421"``, and write three keys back into state:
``advance_registration_<role>``, ``reply``, ``dependency``, ``registration``.

The tests below are parametrised over the three functions so any future
divergence in behavior will surface immediately.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.tools.advance_to_gnd import advance_to_gnd
from agent.tools.advance_to_gnd_arrival import advance_to_gnd_arrival
from agent.tools.advance_twr import advance_to_twr


# (callable, state_advance_key, expected_dependency)
ADVANCE_TOOLS = [
    pytest.param(advance_to_gnd, "advance_registration_gnd", "GND", id="advance_to_gnd"),
    pytest.param(advance_to_twr, "advance_registration_twr", "TWR", id="advance_to_twr"),
    pytest.param(
        advance_to_gnd_arrival,
        "advance_registration_gnd_arrival",
        "GND",
        id="advance_to_gnd_arrival",
    ),
]


def _ctx(known_aircraft):
    """Build a tool_context-like object with the given known_aircraft list."""
    return SimpleNamespace(state={"known_aircraft": list(known_aircraft)})


@pytest.mark.parametrize("tool, advance_key, expected_dep", ADVANCE_TOOLS)
def test_advance_sets_state_keys(tool, advance_key, expected_dep):
    ctx = _ctx(
        [
            {"registration": "EC-MIG", "callsign": "IBE3421", "dependency": "DEL"},
        ]
    )

    readback = tool("EC-MIG", "121.9", ctx)

    assert readback == "121.9, IBE3421"
    assert ctx.state[advance_key] == "EC-MIG"
    assert ctx.state["dependency"] == expected_dep
    assert ctx.state["registration"] == "EC-MIG"
    assert ctx.state["reply"] == "121.9, IBE3421"


@pytest.mark.parametrize("tool, advance_key, expected_dep", ADVANCE_TOOLS)
def test_advance_uses_registration_when_callsign_missing(tool, advance_key, expected_dep):
    """Aircraft entry exists but has no callsign — fall back to registration."""
    ctx = _ctx([{"registration": "EC-XYZ"}])

    readback = tool("EC-XYZ", "118.1", ctx)

    assert readback == "118.1, EC-XYZ"
    assert ctx.state["reply"] == "118.1, EC-XYZ"


@pytest.mark.parametrize("tool, advance_key, expected_dep", ADVANCE_TOOLS)
def test_advance_uses_registration_when_callsign_null(tool, advance_key, expected_dep):
    """Aircraft entry has callsign=None — treated the same as missing."""
    ctx = _ctx([{"registration": "EC-XYZ", "callsign": None}])

    readback = tool("EC-XYZ", "118.1", ctx)

    assert readback == "118.1, EC-XYZ"


@pytest.mark.parametrize("tool, advance_key, expected_dep", ADVANCE_TOOLS)
def test_advance_unknown_registration_uses_registration_as_callsign(
    tool, advance_key, expected_dep
):
    """Registration not present in known_aircraft — readback uses registration."""
    ctx = _ctx([{"registration": "EC-AAA", "callsign": "IBE111"}])

    readback = tool("EC-MIG", "121.9", ctx)

    assert readback == "121.9, EC-MIG"
    assert ctx.state[advance_key] == "EC-MIG"


@pytest.mark.parametrize("tool, advance_key, expected_dep", ADVANCE_TOOLS)
def test_advance_with_empty_known_aircraft_list(tool, advance_key, expected_dep):
    ctx = _ctx([])

    readback = tool("EC-MIG", "121.9", ctx)

    assert readback == "121.9, EC-MIG"
    assert ctx.state[advance_key] == "EC-MIG"
    assert ctx.state["dependency"] == expected_dep


@pytest.mark.parametrize("tool, advance_key, expected_dep", ADVANCE_TOOLS)
def test_advance_with_missing_known_aircraft_key(tool, advance_key, expected_dep):
    """If known_aircraft key is missing from state entirely."""
    ctx = SimpleNamespace(state={})

    readback = tool("EC-MIG", "121.9", ctx)

    assert readback == "121.9, EC-MIG"
    assert ctx.state[advance_key] == "EC-MIG"


@pytest.mark.parametrize("tool, advance_key, expected_dep", ADVANCE_TOOLS)
def test_advance_picks_first_match_by_registration(tool, advance_key, expected_dep):
    """When two entries share the same registration, the first one wins."""
    ctx = _ctx(
        [
            {"registration": "EC-MIG", "callsign": "FIRST"},
            {"registration": "EC-MIG", "callsign": "SECOND"},
            {"registration": "EC-OTHER", "callsign": "OTHER"},
        ]
    )

    readback = tool("EC-MIG", "121.9", ctx)

    assert readback == "121.9, FIRST"


@pytest.mark.parametrize("tool, advance_key, expected_dep", ADVANCE_TOOLS)
def test_advance_does_not_pollute_other_state_keys(tool, advance_key, expected_dep):
    """Other state keys must be preserved."""
    ctx = SimpleNamespace(
        state={
            "known_aircraft": [{"registration": "EC-MIG", "callsign": "IBE"}],
            "session_id": "abc-123",
            "untouched": "value",
        }
    )

    tool("EC-MIG", "121.9", ctx)

    assert ctx.state["session_id"] == "abc-123"
    assert ctx.state["untouched"] == "value"


# ---------------------------------------------------------------------------
# Cross-tool guard: each tool writes ONLY its own advance key, not the others
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool, own_key, foreign_keys",
    [
        (
            advance_to_gnd,
            "advance_registration_gnd",
            ("advance_registration_twr", "advance_registration_gnd_arrival"),
        ),
        (
            advance_to_twr,
            "advance_registration_twr",
            ("advance_registration_gnd", "advance_registration_gnd_arrival"),
        ),
        (
            advance_to_gnd_arrival,
            "advance_registration_gnd_arrival",
            ("advance_registration_gnd", "advance_registration_twr"),
        ),
    ],
)
def test_advance_writes_only_its_own_advance_key(tool, own_key, foreign_keys):
    """Critical: runner.py inspects exactly one of three keys to know which
    handoff happened. A leak across keys would cause double-dispatch."""
    ctx = _ctx([{"registration": "EC-MIG", "callsign": "IBE3421"}])

    tool("EC-MIG", "121.9", ctx)

    assert ctx.state[own_key] == "EC-MIG"
    for fk in foreign_keys:
        assert fk not in ctx.state, f"tool leaked into foreign key {fk}"


def test_readback_format_with_decimal_frequency():
    """Readback must include the decimal frequency exactly as spoken."""
    ctx = _ctx([{"registration": "EC-MIG", "callsign": "IBE3421"}])
    assert advance_to_gnd("EC-MIG", "121.9", ctx) == "121.9, IBE3421"
    assert advance_to_twr("EC-MIG", "118.330", ctx) == "118.330, IBE3421"
