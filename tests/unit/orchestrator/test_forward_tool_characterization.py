"""Characterization tests for ``agent/tools/forward.py::forward_to_agent``.

`forward_to_agent` is the orchestrator's central routing tool (fan-in 21, 125
lines): it resolves the target Cloud Run agent, builds a phase-dependent
payload, performs the HTTP call, records the reply for the debrief, optionally
kicks off a taxi dispatch, and writes four keys into session state that
`runner.py` reads afterwards.

`test_forward_tool.py` already covers the main paths. This module pins down the
*decision boundaries* between them — which branch a given input lands in, which
side effects fire and which are skipped, and what happens on the failure paths.
Those boundaries are exactly what a "split this into helpers" refactor is most
likely to move by accident.

These are characterization tests: they assert what the code does **today**, so
the refactor can be shown to change nothing. Debatable behavior is flagged in
the docstrings rather than "fixed".
"""

from __future__ import annotations

import json
import sys
import types
from types import SimpleNamespace

import httpx
import pytest
import respx
from agent.tools import forward as forward_mod

# ---------------------------------------------------------------------------
# Fixtures (local to this module — tests/conftest.py is intentionally untouched)
# ---------------------------------------------------------------------------


@pytest.fixture
def configured_urls(monkeypatch):
    """Point forward.py at deterministic URLs for the test."""
    monkeypatch.setitem(forward_mod._ROUTES, "DEL", ("http://del.test", "/agents/delivery/run"))
    monkeypatch.setitem(forward_mod._ROUTES, "GND", ("http://gnd.test", "/agents/ground/run"))
    monkeypatch.setitem(forward_mod._ROUTES, "TWR", ("http://twr.test", "/agents/tower/run"))
    monkeypatch.setattr(forward_mod, "_FLIGHT_PLAN_URL", "http://fp.test")
    monkeypatch.setattr(forward_mod, "_WEATHER_URL", "http://wx.test")


@pytest.fixture
def captured_log(monkeypatch):
    """Capture session_log.append_agent_reply calls instead of hitting Redis."""
    captured: list[dict] = []
    monkeypatch.setattr(forward_mod, "append_agent_reply", lambda **kw: captured.append(kw))
    return captured


@pytest.fixture
def captured_dispatch(monkeypatch):
    """Capture dispatch_taxi_plan calls (imported lazily inside the tool)."""
    captured: list[dict] = []

    fake_router = types.ModuleType("shared.services.taxi_router")
    fake_router.dispatch_taxi_plan = lambda merged, **kw: captured.append({"merged": merged, "kwargs": kw})
    if "shared.services.taxi_router" in sys.modules:
        original = sys.modules["shared.services.taxi_router"]
        for attr in dir(original):
            if not attr.startswith("_") and not hasattr(fake_router, attr):
                setattr(fake_router, attr, getattr(original, attr))
    monkeypatch.setitem(sys.modules, "shared.services.taxi_router", fake_router)
    return captured


def _ctx(session_id="sess-1", known_aircraft=None, **extra_state):
    state = {"session_id": session_id, "known_aircraft": known_aircraft or []}
    state.update(extra_state)
    return SimpleNamespace(state=state)


def _payload_of(route) -> dict:
    return json.loads(route.calls[0].request.read())


# ---------------------------------------------------------------------------
# Target resolution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dependency, expected_url",
    [
        ("GND", "http://gnd.test/agents/ground/run"),
        ("gnd", "http://gnd.test/agents/ground/run"),
        ("GnD", "http://gnd.test/agents/ground/run"),
        ("TWR", "http://twr.test/agents/tower/run"),
        ("twr", "http://twr.test/agents/tower/run"),
    ],
)
@respx.mock
def test_dependency_is_upper_cased_before_routing(configured_urls, captured_log, dependency, expected_url):
    route = respx.post(expected_url).mock(return_value=httpx.Response(200, json={"reply": "ok"}))
    known = [{"registration": "EC-MIG", "callsign": "IBE"}]

    forward_mod.forward_to_agent(dependency, "EC-MIG", "msg", _ctx(known_aircraft=known))

    assert route.called


@pytest.mark.parametrize("dependency", ["", "APP", "who-knows", "DELIVERY"])
@respx.mock
def test_any_unrecognised_dependency_falls_back_to_del(configured_urls, captured_log, dependency):
    """Note the fallback normalises the *route* to DEL and also reports DEL in
    ``state["dependency"]`` — the caller never learns the original value."""
    respx.get("http://fp.test/plans/EC-MIG").mock(return_value=httpx.Response(404))
    respx.post("http://del.test/agents/delivery/run").mock(return_value=httpx.Response(200, json={"reply": "ok"}))
    ctx = _ctx()

    forward_mod.forward_to_agent(dependency, "EC-MIG", "msg", ctx)

    assert ctx.state["dependency"] == "DEL"


def test_unconfigured_agent_url_returns_early_without_any_side_effect(monkeypatch, captured_log, captured_dispatch):
    """The "not configured" guard returns before the state writes — so
    ``reply``/``dependency``/``registration`` are NOT set, and nothing is
    logged. `runner.py` therefore falls back to the raw final LLM text."""
    monkeypatch.setitem(forward_mod._ROUTES, "TWR", ("", "/agents/tower/run"))
    ctx = _ctx(known_aircraft=[{"registration": "EC-MIG", "callsign": "IBE"}])

    reply = forward_mod.forward_to_agent("TWR", "EC-MIG", "msg", ctx)

    assert reply == "[ERROR] TWR agent is not configured"
    assert "reply" not in ctx.state
    assert "dependency" not in ctx.state
    assert "registration" not in ctx.state
    assert captured_log == []
    assert captured_dispatch == []


# ---------------------------------------------------------------------------
# DEL branch: which inputs actually take it
# ---------------------------------------------------------------------------


@respx.mock
def test_del_without_registration_takes_the_clearance_branch_not_the_prefetch_branch(configured_urls, captured_log):
    """The pre-fetch guard is ``dep == "DEL" and registration``. An empty
    registration therefore routes to DEL but builds a GND-style payload from
    ``known_aircraft`` — no flight_plan/atis keys at all."""
    route = respx.post("http://del.test/agents/delivery/run").mock(
        return_value=httpx.Response(200, json={"reply": "ok"})
    )
    known = [{"registration": "", "callsign": "IBE", "squawk": 1234}]

    forward_mod.forward_to_agent("DEL", "", "msg", _ctx(known_aircraft=known))

    payload = _payload_of(route)
    assert "flight_plan" not in payload
    assert "atis" not in payload
    assert payload["clearance_data"] == {"callsign": "IBE", "squawk": 1234}


@respx.mock
def test_del_accepts_the_lower_case_departure_icao_spelling(configured_urls, captured_log):
    """The flight plan service has shipped both ``departure_ICAO`` and
    ``departure_icao``; the upper-case one wins, the lower-case one is the
    documented fallback."""
    respx.get("http://fp.test/plans/EC-MIG").mock(return_value=httpx.Response(200, json={"departure_icao": "LEBL"}))
    atis = respx.get("http://wx.test/atis/LEBL").mock(return_value=httpx.Response(200, json={"info": "ATIS-B"}))
    route = respx.post("http://del.test/agents/delivery/run").mock(
        return_value=httpx.Response(200, json={"reply": "ok"})
    )

    forward_mod.forward_to_agent("DEL", "EC-MIG", "msg", _ctx())

    assert atis.called
    assert _payload_of(route)["atis"] == {"info": "ATIS-B"}


@respx.mock
def test_del_upper_case_departure_icao_wins_over_lower_case(configured_urls, captured_log):
    respx.get("http://fp.test/plans/EC-MIG").mock(
        return_value=httpx.Response(200, json={"departure_ICAO": "LEST", "departure_icao": "LEBL"})
    )
    atis = respx.get("http://wx.test/atis/LEST").mock(return_value=httpx.Response(200, json={"info": "ATIS-A"}))
    respx.post("http://del.test/agents/delivery/run").mock(return_value=httpx.Response(200, json={"reply": "ok"}))

    forward_mod.forward_to_agent("DEL", "EC-MIG", "msg", _ctx())

    assert atis.called


@respx.mock
def test_del_skips_both_fetches_when_the_upstream_urls_are_unset(monkeypatch, captured_log):
    """No FLIGHT_PLAN_SERVICE_URL / WEATHER_SERVICE_URL in the environment: the
    keys are still present in the payload, both set to None, and no HTTP call
    to those services is attempted."""
    monkeypatch.setitem(forward_mod._ROUTES, "DEL", ("http://del.test", "/agents/delivery/run"))
    monkeypatch.setattr(forward_mod, "_FLIGHT_PLAN_URL", "")
    monkeypatch.setattr(forward_mod, "_WEATHER_URL", "")
    route = respx.post("http://del.test/agents/delivery/run").mock(
        return_value=httpx.Response(200, json={"reply": "ok"})
    )

    forward_mod.forward_to_agent("DEL", "EC-MIG", "msg", _ctx())

    payload = _payload_of(route)
    assert payload["flight_plan"] is None
    assert payload["atis"] is None
    assert len(respx.calls) == 1  # only the agent POST


@respx.mock
def test_del_context_fetch_network_error_degrades_to_none(configured_urls, captured_log):
    """A dead flight plan / weather service must not break the DEL call."""
    respx.get("http://fp.test/plans/EC-MIG").mock(side_effect=httpx.ConnectError("down"))
    route = respx.post("http://del.test/agents/delivery/run").mock(
        return_value=httpx.Response(200, json={"reply": "ok"})
    )

    reply = forward_mod.forward_to_agent("DEL", "EC-MIG", "msg", _ctx())

    assert reply == "ok"
    payload = _payload_of(route)
    assert payload["flight_plan"] is None
    assert payload["atis"] is None


@respx.mock
def test_del_atis_error_leaves_the_flight_plan_intact(configured_urls, captured_log):
    respx.get("http://fp.test/plans/EC-MIG").mock(return_value=httpx.Response(200, json={"departure_ICAO": "LEST"}))
    respx.get("http://wx.test/atis/LEST").mock(side_effect=httpx.ConnectError("down"))
    route = respx.post("http://del.test/agents/delivery/run").mock(
        return_value=httpx.Response(200, json={"reply": "ok"})
    )

    forward_mod.forward_to_agent("DEL", "EC-MIG", "msg", _ctx())

    payload = _payload_of(route)
    assert payload["flight_plan"] == {"departure_ICAO": "LEST"}
    assert payload["atis"] is None


@pytest.mark.parametrize("status", [400, 404, 500, 503])
@respx.mock
def test_del_non_200_context_responses_become_none(configured_urls, captured_log, status):
    """Only HTTP 200 counts — anything else is discarded silently."""
    respx.get("http://fp.test/plans/EC-MIG").mock(return_value=httpx.Response(status))
    route = respx.post("http://del.test/agents/delivery/run").mock(
        return_value=httpx.Response(200, json={"reply": "ok"})
    )

    forward_mod.forward_to_agent("DEL", "EC-MIG", "msg", _ctx())

    assert _payload_of(route)["flight_plan"] is None


# ---------------------------------------------------------------------------
# GND/TWR branch: clearance_data assembly
# ---------------------------------------------------------------------------


@respx.mock
def test_clearance_data_key_is_omitted_entirely_when_nothing_is_known(configured_urls, captured_log):
    """Unknown registration and no taxi route: the payload carries only
    ``session_id`` and ``message`` — the key is absent, not empty."""
    route = respx.post("http://gnd.test/agents/ground/run").mock(return_value=httpx.Response(200, json={"reply": "ok"}))

    forward_mod.forward_to_agent("GND", "EC-UNKNOWN", "msg", _ctx(known_aircraft=[]))

    assert _payload_of(route) == {"session_id": "sess-1", "message": "msg"}


@respx.mock
def test_taxi_route_alone_is_enough_to_create_clearance_data(configured_urls, captured_log):
    """Even for an aircraft with no stored clearance, a successful taxi route
    materialises ``clearance_data`` with just that one key."""
    route = respx.post("http://gnd.test/agents/ground/run").mock(return_value=httpx.Response(200, json={"reply": "ok"}))
    taxi_route = {"success": True, "waypoints": [{"lat": 41.0, "lon": 2.0}]}

    forward_mod.forward_to_agent("GND", "EC-UNKNOWN", "taxi", _ctx(known_aircraft=[]), taxi_route=taxi_route)

    assert _payload_of(route)["clearance_data"] == {"taxi_route": taxi_route}


@respx.mock
def test_taxi_route_without_success_key_is_not_merged(configured_urls, captured_log):
    """The guard is ``taxi_route.get("success")`` — a route dict that simply
    omits the flag is dropped exactly like an explicit failure."""
    known = [{"registration": "EC-MIG", "callsign": "IBE"}]
    route = respx.post("http://gnd.test/agents/ground/run").mock(return_value=httpx.Response(200, json={"reply": "ok"}))

    forward_mod.forward_to_agent(
        "GND",
        "EC-MIG",
        "taxi",
        _ctx(known_aircraft=known),
        taxi_route={"waypoints": [{"lat": 41.0, "lon": 2.0}]},
    )

    assert "taxi_route" not in _payload_of(route)["clearance_data"]


@respx.mock
def test_clearance_data_takes_the_first_match_and_strips_three_keys(configured_urls, captured_log):
    """Duplicate registrations in ``known_aircraft`` resolve to the first
    entry; ``registration``/``dependency``/``source`` never reach the agent."""
    known = [
        {"registration": "EC-MIG", "dependency": "GND", "source": "db", "squawk": 1111},
        {"registration": "EC-MIG", "dependency": "GND", "source": "redis", "squawk": 2222},
    ]
    route = respx.post("http://gnd.test/agents/ground/run").mock(return_value=httpx.Response(200, json={"reply": "ok"}))

    forward_mod.forward_to_agent("GND", "EC-MIG", "msg", _ctx(known_aircraft=known))

    assert _payload_of(route)["clearance_data"] == {"squawk": 1111}


@respx.mock
def test_missing_known_aircraft_state_key_is_tolerated(configured_urls, captured_log):
    """``known_aircraft`` absent from state entirely (not just empty)."""
    route = respx.post("http://twr.test/agents/tower/run").mock(return_value=httpx.Response(200, json={"reply": "ok"}))
    ctx = SimpleNamespace(state={"session_id": "sess-1"})

    reply = forward_mod.forward_to_agent("TWR", "EC-MIG", "msg", ctx)

    assert reply == "ok"
    assert "clearance_data" not in _payload_of(route)


@respx.mock
def test_session_id_missing_from_state_is_sent_as_empty_string(configured_urls, captured_log):
    route = respx.post("http://twr.test/agents/tower/run").mock(return_value=httpx.Response(200, json={"reply": "ok"}))

    forward_mod.forward_to_agent("TWR", "EC-MIG", "msg", SimpleNamespace(state={}))

    assert _payload_of(route)["session_id"] == ""


# ---------------------------------------------------------------------------
# Response handling and state writes
# ---------------------------------------------------------------------------


@respx.mock
def test_response_without_a_reply_key_yields_empty_reply_and_no_session_log(configured_urls, captured_log):
    """A malformed agent response degrades to an empty reply; the state key is
    still written (as ""), but nothing is appended to the debrief log."""
    respx.post("http://twr.test/agents/tower/run").mock(
        return_value=httpx.Response(200, json={"clearance_data": {"squawk": 7000}})
    )
    ctx = _ctx()

    reply = forward_mod.forward_to_agent("TWR", "EC-MIG", "msg", ctx)

    assert reply == ""
    assert ctx.state["reply"] == ""
    assert ctx.state["clearance_data"] == {"squawk": 7000}
    assert captured_log == []


@respx.mock
def test_empty_registration_is_normalised_to_none_in_state(configured_urls, captured_log):
    """`runner.py` treats ``registration`` as optional — an empty string would
    otherwise be persisted as a bogus aircraft key."""
    respx.post("http://twr.test/agents/tower/run").mock(return_value=httpx.Response(200, json={"reply": "ok"}))
    ctx = _ctx()

    forward_mod.forward_to_agent("TWR", "", "msg", ctx)

    assert ctx.state["registration"] is None


@respx.mock
def test_clearance_data_state_key_is_none_when_the_agent_omits_it(configured_urls, captured_log):
    """Always written, never left stale — `runner.py` reads it unconditionally."""
    respx.post("http://twr.test/agents/tower/run").mock(return_value=httpx.Response(200, json={"reply": "ok"}))
    ctx = _ctx()
    ctx.state["clearance_data"] = {"stale": True}

    forward_mod.forward_to_agent("TWR", "EC-MIG", "msg", ctx)

    assert ctx.state["clearance_data"] is None


@respx.mock
def test_http_failure_still_writes_all_four_state_keys(configured_urls, captured_log):
    """The error path is not an early return: state stays consistent so
    `runner.py` can surface the error text to the controller."""
    respx.post("http://gnd.test/agents/ground/run").mock(return_value=httpx.Response(503))
    ctx = _ctx(known_aircraft=[{"registration": "EC-MIG", "callsign": "IBE"}])

    reply = forward_mod.forward_to_agent("GND", "EC-MIG", "msg", ctx)

    assert reply == "[ERROR] GND agent returned HTTP 503"
    assert ctx.state["reply"] == reply
    assert ctx.state["dependency"] == "GND"
    assert ctx.state["registration"] == "EC-MIG"
    assert ctx.state["clearance_data"] is None


@respx.mock
def test_error_replies_are_written_to_the_debrief_log(configured_urls, captured_log):
    """The append guard is only ``reply and session_id`` — error strings count
    as replies, so the instructor's timeline records the outage."""
    respx.post("http://gnd.test/agents/ground/run").mock(side_effect=httpx.ConnectError("refused"))

    forward_mod.forward_to_agent("GND", "EC-MIG", "msg", _ctx(known_aircraft=[{"registration": "EC-MIG"}]))

    assert len(captured_log) == 1
    assert captured_log[0]["reply"].startswith("[ERROR] could not reach GND agent")
    assert captured_log[0]["taxi_data"] is None


@respx.mock
def test_session_log_callsign_comes_from_taxi_data_not_known_aircraft(configured_urls, captured_log, captured_dispatch):
    """The ``callsign`` recorded for the debrief is whatever the pilot agent
    echoed back in ``taxi_data.aircraft_registration`` — and it is None
    whenever the agent sent no taxi_data at all."""
    respx.post("http://gnd.test/agents/ground/run").mock(
        return_value=httpx.Response(
            200,
            json={
                "reply": "Push approved",
                "taxi_data": {"pushback_approved": True, "aircraft_registration": "IBE3421"},
            },
        )
    )

    forward_mod.forward_to_agent("GND", "EC-MIG", "pushback", _ctx(known_aircraft=[{"registration": "EC-MIG"}]))

    assert captured_log[0]["callsign"] == "IBE3421"
    assert captured_log[0]["taxi_data"] == {
        "pushback_approved": True,
        "aircraft_registration": "IBE3421",
    }


# ---------------------------------------------------------------------------
# Taxi dispatch trigger
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "taxi_data, should_dispatch",
    [
        ({"pushback_approved": True}, True),
        ({"taxi_route": "T E1"}, True),
        ({"pushback_approved": True, "taxi_route": "T E1"}, True),
        ({"pushback_approved": False, "taxi_route": "T E1"}, True),
        ({"pushback_approved": False}, False),
        ({"pushback_approved": False, "taxi_route": ""}, False),
        ({"pushback_approved": False, "taxi_route": "   "}, False),
        ({"taxi_route": None}, False),
        ({}, False),
        (None, False),
    ],
)
@respx.mock
def test_gnd_dispatch_trigger_truth_table(configured_urls, captured_log, captured_dispatch, taxi_data, should_dispatch):
    """A whitespace-only taxi_route does not count; a falsy pushback flag alone
    does not either. Both are stripped/booled before the OR."""
    body = {"reply": "ok"}
    if taxi_data is not None:
        body["taxi_data"] = taxi_data
    respx.post("http://gnd.test/agents/ground/run").mock(return_value=httpx.Response(200, json=body))

    forward_mod.forward_to_agent("GND", "EC-MIG", "msg", _ctx(known_aircraft=[{"registration": "EC-MIG"}]))

    assert bool(captured_dispatch) is should_dispatch


@respx.mock
def test_dispatch_is_skipped_when_registration_is_empty(configured_urls, captured_log, captured_dispatch):
    respx.post("http://gnd.test/agents/ground/run").mock(
        return_value=httpx.Response(200, json={"reply": "ok", "taxi_data": {"pushback_approved": True}})
    )

    forward_mod.forward_to_agent("GND", "", "msg", _ctx())

    assert captured_dispatch == []


@respx.mock
def test_twr_never_dispatches_a_taxi_plan(configured_urls, captured_log, captured_dispatch):
    respx.post("http://twr.test/agents/tower/run").mock(
        return_value=httpx.Response(200, json={"reply": "ok", "taxi_data": {"pushback_approved": True}})
    )

    forward_mod.forward_to_agent("TWR", "EC-MIG", "msg", _ctx())

    assert captured_dispatch == []


@respx.mock
def test_dispatch_payload_shape_is_exactly_three_merged_keys(configured_urls, captured_log, captured_dispatch):
    """The taxi router receives the *A\\* route*, the *agent's structured taxi
    data*, and the *pilot readback* — plus the controller's original
    instruction as a separate kwarg. This is the taxi-router contract."""
    taxi_route = {"success": True, "waypoints": [{"lat": 41.0, "lon": 2.0}]}
    taxi_data = {"taxi_route": "T E1", "aircraft_registration": "IBE3421"}
    respx.post("http://gnd.test/agents/ground/run").mock(
        return_value=httpx.Response(200, json={"reply": "Taxi via T to E1, IBE3421", "taxi_data": taxi_data})
    )

    forward_mod.forward_to_agent(
        "GND",
        "EC-MIG",
        "IBE3421 taxi to holding point E1 via T",
        _ctx(session_id="sess-42", known_aircraft=[{"registration": "EC-MIG"}]),
        taxi_route=taxi_route,
    )

    assert len(captured_dispatch) == 1
    assert captured_dispatch[0]["merged"] == {
        "taxi_route": taxi_route,
        "taxi_data": taxi_data,
        "instruction_text": "Taxi via T to E1, IBE3421",
    }
    assert captured_dispatch[0]["kwargs"] == {
        "pilot_readback_text": "Taxi via T to E1, IBE3421",
        "registration": "EC-MIG",
        "controller_instruction": "IBE3421 taxi to holding point E1 via T",
        "callsign": "IBE3421",
        "session_id": "sess-42",
    }


@respx.mock
def test_dispatch_callsign_falls_back_to_registration(configured_urls, captured_log, captured_dispatch):
    respx.post("http://gnd.test/agents/ground/run").mock(
        return_value=httpx.Response(200, json={"reply": "ok", "taxi_data": {"pushback_approved": True}})
    )

    forward_mod.forward_to_agent("GND", "EC-MIG", "msg", _ctx(known_aircraft=[{"registration": "EC-MIG"}]))

    assert captured_dispatch[0]["kwargs"]["callsign"] == "EC-MIG"


@respx.mock
def test_dispatch_merges_a_failed_taxi_route_unchanged(configured_urls, captured_log, captured_dispatch):
    """``taxi_route`` is forwarded to the router verbatim even when it was not
    merged into the agent payload — the success filter applies only upstream."""
    failed_route = {"success": False, "error": "no route"}
    respx.post("http://gnd.test/agents/ground/run").mock(
        return_value=httpx.Response(200, json={"reply": "ok", "taxi_data": {"pushback_approved": True}})
    )

    forward_mod.forward_to_agent(
        "GND",
        "EC-MIG",
        "msg",
        _ctx(known_aircraft=[{"registration": "EC-MIG"}]),
        taxi_route=failed_route,
    )

    assert captured_dispatch[0]["merged"]["taxi_route"] == failed_route


@respx.mock
def test_dispatch_runs_after_the_session_log_and_before_the_state_writes(configured_urls, captured_log, monkeypatch):
    """Ordering guard: if dispatch blows up, the debrief entry has already been
    written but the state keys have NOT — and the tool still returns the reply.
    A refactor that moves the state writes above the dispatch would change what
    `runner.py` sees on a dispatch failure."""
    fake_router = types.ModuleType("shared.services.taxi_router")

    def _boom(*_, **__):
        raise RuntimeError("router exploded")

    fake_router.dispatch_taxi_plan = _boom
    monkeypatch.setitem(sys.modules, "shared.services.taxi_router", fake_router)
    respx.post("http://gnd.test/agents/ground/run").mock(
        return_value=httpx.Response(200, json={"reply": "Push approved", "taxi_data": {"pushback_approved": True}})
    )
    ctx = _ctx(known_aircraft=[{"registration": "EC-MIG"}])

    reply = forward_mod.forward_to_agent("GND", "EC-MIG", "msg", ctx)

    assert reply == "Push approved"
    assert len(captured_log) == 1
    assert ctx.state["reply"] == "Push approved"


@respx.mock
def test_no_session_log_and_no_state_pollution_when_session_id_is_empty(
    configured_urls, captured_log, captured_dispatch
):
    """An empty session_id suppresses the debrief entry but NOT the dispatch —
    the aircraft still moves, the instructor just loses the line."""
    respx.post("http://gnd.test/agents/ground/run").mock(
        return_value=httpx.Response(200, json={"reply": "ok", "taxi_data": {"pushback_approved": True}})
    )

    forward_mod.forward_to_agent(
        "GND", "EC-MIG", "msg", _ctx(session_id="", known_aircraft=[{"registration": "EC-MIG"}])
    )

    assert captured_log == []
    assert len(captured_dispatch) == 1
    assert captured_dispatch[0]["kwargs"]["session_id"] == ""


# ---------------------------------------------------------------------------
# Contract guard: the ADK tool signature the LLM sees
# ---------------------------------------------------------------------------


def test_public_signature_is_stable():
    """The ADK builds the tool's JSON schema from this signature and docstring;
    renaming or reordering a parameter silently changes the agent contract."""
    import inspect

    sig = inspect.signature(forward_mod.forward_to_agent)
    assert list(sig.parameters) == [
        "dependency",
        "registration",
        "message",
        "tool_context",
        "taxi_route",
    ]
    assert sig.parameters["taxi_route"].default is None
    assert forward_mod.forward_to_agent.__doc__ is not None
