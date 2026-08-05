"""TWR runner — the generic pilot runner configured for Tower."""

import logging
from typing import Any

from agent.agent import twr_agent

from shared.agent_runner import AgentRunnerConfig, ContextField, build_run_agent

logger = logging.getLogger(__name__)

CONFIG = AgentRunnerConfig(
    label="TWR",
    app_name="airport_twr",
    text_key="reply_text",
    data_key="reply_data",
    context_fields=(ContextField("clearance_data", "Clearance data: {value}"),),
)

_run_agent = build_run_agent(agent=twr_agent, config=CONFIG, logger=logger)


def run_agent(
    session_id: str,
    message: str,
    clearance_data: dict | None = None,
) -> dict[str, Any]:
    """Draft the tower readback. Returns ``{"reply", "reply_data"}``."""
    return _run_agent(session_id, message, clearance_data=clearance_data)
