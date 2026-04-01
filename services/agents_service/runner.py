import asyncio
import logging
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from agents.delivery.agent import build_del_agent

logger = logging.getLogger(__name__)

_APP_NAME = "airport_del"


def run_del_agent(
    session_id: str,
    message: str,
    flight_plan: dict | None = None,
    atis: dict | None = None,
) -> dict[str, Any]:
    """
    Run the DEL agent for a single dispatch request.

    Returns:
        dict with keys:
          - reply          (str)       : clearance text spoken to the pilot
          - clearance_data (dict|None) : structured clearance fields, if issued
    """
    context: dict[str, Any] = {}
    agent = build_del_agent(context)

    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name=_APP_NAME,
        session_service=session_service,
    )

    # Append flight plan and ATIS to the message so the agent has full context
    enriched = message
    if flight_plan or atis:
        parts = [message, "\n\n[CONTEXT]"]
        if flight_plan:
            parts.append(f"Flight plan: {flight_plan}")
        if atis:
            parts.append(f"ATIS: {atis}")
        enriched = "\n".join(parts)

    user_content = Content(role="user", parts=[Part(text=enriched)])

    async def _run() -> str:
        await session_service.create_session(
            app_name=_APP_NAME,
            user_id="pilot",
            session_id=session_id,
        )
        final_text = ""
        async for event in runner.run_async(
            user_id="pilot",
            session_id=session_id,
            new_message=user_content,
        ):
            if event.is_final_response() and event.content and event.content.parts:
                final_text = "".join(
                    p.text for p in event.content.parts if hasattr(p, "text")
                )
        return final_text

    reply = asyncio.run(_run())

    return {
        "reply": context.get("clearance_data", {}).get("clearance_text") or reply,
        "clearance_data": context.get("clearance_data"),
    }
