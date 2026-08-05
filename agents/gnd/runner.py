"""GND runner — the generic pilot runner configured for Ground."""

import logging
from typing import Any

from agent.agent import gnd_agent

from shared.agent_runner import AgentRunnerConfig, ContextField, build_run_agent

logger = logging.getLogger(__name__)

CONFIG = AgentRunnerConfig(
    label="GND",
    app_name="airport_gnd",
    text_key="instruction_text",
    data_key="taxi_data",
    context_fields=(ContextField("clearance_data", "Clearance data: {value}"),),
    # GND opens the context section with a single newline, unlike DEL and TWR.
    context_header="\n[CONTEXT]",
)

_run_agent = build_run_agent(agent=gnd_agent, config=CONFIG, logger=logger)


def run_agent(
    session_id: str,
    message: str,
    clearance_data: dict | None = None,
) -> dict[str, Any]:
    """Draft the pushback/taxi readback. Returns ``{"reply", "taxi_data"}``."""
    return _run_agent(session_id, message, clearance_data=clearance_data)
