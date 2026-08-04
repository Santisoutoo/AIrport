"""Unit tests for agent/tools/taxi_route.py::get_taxi_route.

The function pulls together three helpers from shared.services.taxi_router
(extract_destination, extract_taxiway_tokens, _load_graph) plus the public
compute_taxi_route. The tests below stub all four to isolate the routing
logic implemented in this module:

  * destination extraction and via-list cleanup
  * fall-back: last via token becomes destination if regex missed it
  * removal of destination from via list when both contain the same token
  * graceful handling of a graph that fails to load

Stubs are installed with monkeypatch so each test is independent.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.tools import taxi_route as taxi_route_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stub_router(monkeypatch, *, destination, via, graph_tokens=None, raise_graph=False):
    """Install stubs for the three shared.services.taxi_router helpers used."""

    def _fake_extract_destination(text):
        return destination

    def _fake_extract_taxiway_tokens(
        *, taxi_route_text, fallback_text, known_tokens, dedup=True,
    ):
        # Echo the via list -- known_tokens is asserted via call recording
        _fake_extract_taxiway_tokens.last_call = {
            "taxi_route_text": taxi_route_text,
            "fallback_text": fallback_text,
            "known_tokens": known_tokens,
            "dedup": dedup,
        }
        return list(via)

    if raise_graph:
        def _fake_load_graph():
            raise RuntimeError("graph load failed")
    else:
        def _fake_load_graph():
            class _G:
                _nodes_by_taxiway = {t: object() for t in (graph_tokens or [])}

            return _G()

    monkeypatch.setattr(
        "shared.services.taxi_router.destination_parser.extract_destination",
        _fake_extract_destination,
    )
    monkeypatch.setattr(
        "shared.services.taxi_router.readback_parser.extract_taxiway_tokens",
        _fake_extract_taxiway_tokens,
    )
    monkeypatch.setattr(
        "shared.services.taxi_router.router._load_graph",
        _fake_load_graph,
    )
    return _fake_extract_taxiway_tokens


def _stub_compute(monkeypatch, response):
    """Install a stub for compute_taxi_route returning a fixed dict.

    Records the call args on the returned callable for later assertions.
    """

    def _fake_compute(*, destination, via, callsign):
        _fake_compute.last_call = {
            "destination": destination,
            "via": via,
            "callsign": callsign,
        }
        return response

    monkeypatch.setattr(taxi_route_mod, "compute_taxi_route", _fake_compute)
    return _fake_compute


def _ctx():
    return SimpleNamespace(state={})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_returns_failure_when_no_destination_extractable(monkeypatch):
    _stub_router(monkeypatch, destination=None, via=[])
    _stub_compute(monkeypatch, response={"success": True})

    result = taxi_route_mod.get_taxi_route("EC-MIG", "cleared takeoff", _ctx())

    assert result["success"] is False
    assert "No destination" in result["error"]


def test_strips_destination_token_from_via_list(monkeypatch):
    """If 'E1' appears as both destination and via, it must be removed from via."""
    _stub_router(monkeypatch, destination="E1", via=["E1", "T"])
    compute = _stub_compute(monkeypatch, response={"success": True, "waypoints": []})

    taxi_route_mod.get_taxi_route("EC-MIG", "taxi to E1 via E1 T", _ctx())

    assert compute.last_call["via"] == ["T"]
    assert compute.last_call["destination"] == "E1"


def test_falls_back_to_last_via_as_destination_when_no_explicit_dest(monkeypatch):
    """No destination from regex -> last token in via is treated as destination."""
    _stub_router(monkeypatch, destination=None, via=["T", "E1"])
    compute = _stub_compute(monkeypatch, response={"success": True})

    taxi_route_mod.get_taxi_route("EC-MIG", "via T E1", _ctx())

    assert compute.last_call["destination"] == "E1"
    assert compute.last_call["via"] == ["T"]


def test_passes_registration_as_callsign(monkeypatch):
    """compute_taxi_route receives the registration as ``callsign``."""
    _stub_router(monkeypatch, destination="E1", via=["T"])
    compute = _stub_compute(monkeypatch, response={"success": True})

    taxi_route_mod.get_taxi_route("EI-MQE", "taxi to E1 via T", _ctx())

    assert compute.last_call["callsign"] == "EI-MQE"


def test_graph_load_failure_does_not_block_routing(monkeypatch):
    """A graph load exception must be swallowed and routing continues with known_tokens=None."""
    parser = _stub_router(monkeypatch, destination="E1", via=["T"], raise_graph=True)
    _stub_compute(monkeypatch, response={"success": True})

    taxi_route_mod.get_taxi_route("EC-MIG", "taxi to E1 via T", _ctx())

    assert parser.last_call["known_tokens"] is None


def test_passes_known_tokens_when_graph_loads(monkeypatch):
    """When the graph loads, its taxiway keys are forwarded to the parser as known_tokens."""
    parser = _stub_router(
        monkeypatch, destination="E1", via=["T"], graph_tokens=["T", "Y", "Z"]
    )
    _stub_compute(monkeypatch, response={"success": True})

    taxi_route_mod.get_taxi_route("EC-MIG", "taxi to E1 via T", _ctx())

    assert parser.last_call["known_tokens"] is not None
    assert set(parser.last_call["known_tokens"]) == {"T", "Y", "Z"}


def test_destination_comparison_is_case_insensitive(monkeypatch):
    """Destination 'e1' must dedupe against via 'E1' regardless of case."""
    _stub_router(monkeypatch, destination="e1", via=["E1", "T"])
    compute = _stub_compute(monkeypatch, response={"success": True})

    taxi_route_mod.get_taxi_route("EC-MIG", "taxi to e1 via E1 T", _ctx())

    assert compute.last_call["via"] == ["T"]


def test_passes_through_compute_route_response(monkeypatch):
    """get_taxi_route returns exactly what compute_taxi_route returned."""
    expected = {
        "success": True,
        "waypoints": [{"lat": 0, "lon": 0}],
        "taxiway_sequence": ["T", "E1"],
        "total_distance_m": 250.5,
    }
    _stub_router(monkeypatch, destination="E1", via=["T"])
    _stub_compute(monkeypatch, response=expected)

    result = taxi_route_mod.get_taxi_route("EC-MIG", "taxi to E1 via T", _ctx())
    assert result == expected
