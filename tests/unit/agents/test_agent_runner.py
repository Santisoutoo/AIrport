"""Unit tests for agents/common/agent_runner.py — the generic pilot runner.

The DEL, GND and TWR runners are now three configurations of ``build_run_agent``,
so this module covers the behavior all three used to duplicate:

* context enrichment (the ``[CONTEXT]`` block appended to the transmission),
* extraction of the agent's JSON block into ``{"reply", <data_key>}``,
* the degraded paths: no JSON, malformed JSON, and an exploding ADK call.

The JSON keys asserted here are the contract the orchestrator's
``forward_to_agent`` consumes — see tests/unit/agents/test_agent_contract.py.
"""

from __future__ import annotations

import pytest

from agents.common.agent_runner import (
    AgentRunnerConfig,
    ContextField,
    build_agent_context,
    build_run_agent,
)
from tests.fixtures.adk_runner import install_fake_runner
import agents.common.agent_runner as agent_runner_mod


DEL_CONFIG = AgentRunnerConfig(
    label="DEL",
    app_name="airport_del",
    text_key="clearance_text",
    data_key="clearance_data",
    context_fields=(
        ContextField("flight_plan", "Flight plan: {value}"),
        ContextField("atis", "ATIS: {value}"),
    ),
)

GND_CONFIG = AgentRunnerConfig(
    label="GND",
    app_name="airport_gnd",
    text_key="instruction_text",
    data_key="taxi_data",
    context_fields=(ContextField("clearance_data", "Clearance data: {value}"),),
    context_header="\n[CONTEXT]",
)


def _build(monkeypatch, config, final_text: str):
    """Build a run_agent backed by a scripted FakeADKRunner."""
    fake = install_fake_runner(monkeypatch, agent_runner_mod)
    fake.script(final_text=final_text)
    run_agent = build_run_agent(agent=object(), config=config)
    return run_agent, fake


def _sent_text(fake) -> str:
    """The prompt text handed to the ADK runner on the last call."""
    return fake.calls[-1]["new_message"].parts[0].text


# ---------------------------------------------------------------------------
# Context enrichment
# ---------------------------------------------------------------------------


def test_context_is_omitted_when_nothing_was_attached():
    assert build_agent_context("Iberia 123, taxi?", DEL_CONFIG, {}) == "Iberia 123, taxi?"
    assert build_agent_context("msg", DEL_CONFIG, {"flight_plan": None, "atis": {}}) == "msg"


def test_context_renders_only_the_fields_that_are_present():
    enriched = build_agent_context("msg", DEL_CONFIG, {"atis": {"letter": "C"}})

    assert enriched == "msg\n\n\n[CONTEXT]\nATIS: {'letter': 'C'}"


def test_context_renders_fields_in_declaration_order():
    enriched = build_agent_context("msg", DEL_CONFIG, {"flight_plan": {"id": 1}, "atis": {"letter": "C"}})

    assert enriched == ("msg\n\n\n[CONTEXT]\nFlight plan: {'id': 1}\nATIS: {'letter': 'C'}")


def test_gnd_keeps_its_single_newline_context_header():
    # GND's header historically differs from DEL/TWR; kept as-is on purpose.
    enriched = build_agent_context("msg", GND_CONFIG, {"clearance_data": {"stand": "A1"}})

    assert enriched == "msg\n\n[CONTEXT]\nClearance data: {'stand': 'A1'}"


def test_run_agent_sends_the_enriched_message_to_the_adk_runner(monkeypatch):
    run_agent, fake = _build(monkeypatch, DEL_CONFIG, final_text="ok")

    run_agent("s1", "Iberia 123, request clearance", flight_plan={"id": 7})

    assert _sent_text(fake) == ("Iberia 123, request clearance\n\n\n[CONTEXT]\nFlight plan: {'id': 7}")


# ---------------------------------------------------------------------------
# JSON extraction and the returned contract
# ---------------------------------------------------------------------------


def test_returns_reply_and_data_under_the_configured_keys(monkeypatch):
    raw = 'Here you go: {"clearance_text": "Cleared to LEPA, squawk 2341", "clearance_data": {"squawk": "2341"}}'
    run_agent, _ = _build(monkeypatch, DEL_CONFIG, final_text=raw)

    result = run_agent("s1", "msg")

    assert result == {
        "reply": "Cleared to LEPA, squawk 2341",
        "clearance_data": {"squawk": "2341"},
    }


def test_gnd_uses_its_own_json_keys(monkeypatch):
    raw = '{"instruction_text": "Taxi via B, C", "taxi_data": {"pushback_approved": true}}'
    run_agent, _ = _build(monkeypatch, GND_CONFIG, final_text=raw)

    result = run_agent("s1", "msg")

    assert result == {
        "reply": "Taxi via B, C",
        "taxi_data": {"pushback_approved": True},
    }


def test_plain_text_reply_falls_back_to_the_raw_text(monkeypatch):
    run_agent, _ = _build(monkeypatch, DEL_CONFIG, final_text="Say again")

    result = run_agent("s1", "msg")

    assert result == {"reply": "Say again", "clearance_data": None}


def test_json_without_the_expected_keys_falls_back_to_the_raw_text(monkeypatch):
    run_agent, _ = _build(monkeypatch, DEL_CONFIG, final_text='{"unrelated": 1}')

    result = run_agent("s1", "msg")

    assert result == {"reply": '{"unrelated": 1}', "clearance_data": None}


def test_malformed_json_is_swallowed_and_logged(monkeypatch, caplog):
    run_agent, _ = _build(monkeypatch, DEL_CONFIG, final_text='{"clearance_text": oops}')

    with caplog.at_level("WARNING"):
        result = run_agent("s1", "msg")

    assert result == {"reply": '{"clearance_text": oops}', "clearance_data": None}
    assert "could not parse JSON" in caplog.text


# ---------------------------------------------------------------------------
# Session handling and failures
# ---------------------------------------------------------------------------


def test_session_is_created_once_and_reused(monkeypatch):
    run_agent, fake = _build(monkeypatch, DEL_CONFIG, final_text="ok")
    session_service = fake.session_service

    run_agent("s1", "first")
    fake.script(final_text="ok")
    run_agent("s1", "second")

    sessions = [k for k in session_service._sessions if k[2] == "s1"]
    assert sessions == [("airport_del", "pilot", "s1")]
    assert len(fake.calls) == 2


def test_adk_failure_returns_the_error_contract(monkeypatch, caplog):
    fake = install_fake_runner(monkeypatch, agent_runner_mod)

    async def _boom(**_):
        raise RuntimeError("vertex is down")
        yield  # pragma: no cover - makes _boom an async generator

    monkeypatch.setattr(fake, "run_async", _boom)
    run_agent = build_run_agent(agent=object(), config=GND_CONFIG)

    with caplog.at_level("ERROR"):
        result = run_agent("s1", "msg")

    assert result == {"reply": "[GND error] agent failed", "taxi_data": None}
    assert "[GND] agent error" in caplog.text


@pytest.mark.parametrize("config", [DEL_CONFIG, GND_CONFIG])
def test_result_always_carries_exactly_two_keys(monkeypatch, config):
    run_agent, _ = _build(monkeypatch, config, final_text="whatever")

    result = run_agent("s1", "msg")

    assert set(result) == {"reply", config.data_key}
