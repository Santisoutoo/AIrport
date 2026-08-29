"""DEL runner — the generic pilot runner configured for Clearance Delivery."""

import logging
from typing import Any

from agent.agent import del_agent
from shared.agent_runner import AgentRunnerConfig, ContextField, build_run_agent

logger = logging.getLogger(__name__)

CONFIG = AgentRunnerConfig(
    label="DEL",
    app_name="airport_del",
    text_key="clearance_text",
    data_key="clearance_data",
    context_fields=(
        ContextField("flight_plan", "Flight plan: {value}"),
        ContextField("atis", "ATIS: {value}"),
    ),
)

_run_agent = build_run_agent(agent=del_agent, config=CONFIG, logger=logger)


def run_agent(
    session_id: str,
    message: str,
    flight_plan: dict | None = None,
    atis: dict | None = None,
) -> dict[str, Any]:
    """Draft the IFR clearance readback. Returns ``{"reply", "clearance_data"}``."""
    return _run_agent(session_id, message, flight_plan=flight_plan, atis=atis)
