"""ADK callbacks for logging and basic metrics collection."""

import logging
import time
from typing import Any

logger = logging.getLogger("agents_service")

# simple metrics
_metrics: dict[str, Any] = {
    "agent_calls_total": 0,
    "agent_errors_total": 0,
    "latency_seconds": [],
}


def on_agent_start(agent_name: str, session_id: str, user_message: str) -> float:
    """Called at the start of an agent turn. Returns a start timestamp."""
    _metrics["agent_calls_total"] += 1
    logger.info("[%s] session=%s | START | message=%r",
                agent_name, session_id, user_message[:120])
    return time.monotonic()


def on_agent_end(
    agent_name: str,
    session_id: str,
    reply: str,
    start_time: float,
    error: Exception | None = None,
) -> None:
    """Called at the end of an agent turn."""
    elapsed = time.monotonic() - start_time
    _metrics["latency_seconds"].append(elapsed)

    if error:
        _metrics["agent_errors_total"] += 1
        logger.error(
            "[%s] session=%s | ERROR | elapsed=%.3fs | error=%s",
            agent_name, session_id, elapsed, error,
        )
    else:
        logger.info(
            "[%s] session=%s | END | elapsed=%.3fs | reply=%r",
            agent_name, session_id, elapsed, reply[:120],
        )


def on_tool_call(agent_name: str, tool_name: str, args: dict) -> None:
    """Called before each tool invocation."""
    logger.debug("[%s] TOOL_CALL | tool=%s | args=%s",
                 agent_name, tool_name, args)


def on_tool_result(agent_name: str, tool_name: str, result: Any) -> None:
    """Called after each tool invocation."""
    logger.debug("[%s] TOOL_RESULT | tool=%s | result=%s",
                 agent_name, tool_name, result)


def get_metrics() -> dict:
    """Return a snapshot of current metrics."""
    latencies = _metrics["latency_seconds"]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    return {
        "agent_calls_total": _metrics["agent_calls_total"],
        "agent_errors_total": _metrics["agent_errors_total"],
        "avg_latency_seconds": round(avg_latency, 4),
    }
