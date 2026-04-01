"""
Orchestrator LLM agent.

The ADK Agent object is built per-request because the tools need access to the
request-scoped SQLAlchemy DB session and session_id.  The LiteLlm model object
is a module-level singleton to avoid re-initialising the client on every call.
"""
from typing import Any

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from sqlalchemy.orm import Session

from config import config
from agent.prompts import SYSTEM_PROMPT
from agent.tools.aircraft import make_get_known_aircraft
from agent.tools.forward import make_forward_to_agent

# Module-level LiteLlm singleton — initialised once, reused across requests.
_model = LiteLlm(model=config.LITELLM_MODEL)


def build_agent(session_id: str, db: Session, context: dict[str, Any]) -> Agent:
    """
    Build and return a fresh ADK Agent for a single dispatch request.

    Args:
        session_id: Unique identifier for this pilot session (passed through to
                    the sub-agents so they can maintain conversation history).
        db:         SQLAlchemy session scoped to the current HTTP request.
        context:    Mutable dict; after the agent finishes, it will contain:
                      "dependency"   — DEL | GND | TWR
                      "registration" — corrected callsign or None
                      "reply"        — the sub-agent's reply text

    Returns:
        A configured ADK Agent ready to be passed to a Runner.
    """
    get_known_aircraft = make_get_known_aircraft(db)
    forward_to_agent = make_forward_to_agent(session_id, db, context)

    return Agent(
        name="ORCH",
        model=_model,
        description="ATC orchestrator — routes pilot messages to DEL, GND, or TWR agents",
        instruction=SYSTEM_PROMPT,
        tools=[get_known_aircraft, forward_to_agent],
    )
