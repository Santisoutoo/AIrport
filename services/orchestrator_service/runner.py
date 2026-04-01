import asyncio
import logging
from typing import Any, Optional

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from sqlalchemy.orm import Session

from agent.agent import build_agent

logger = logging.getLogger(__name__)

_APP_NAME = "airport_orchestrator"


def run_orchestrator_agent(
    session_id: str,
    message: str,
    db: Session,
) -> dict[str, Any]:
    """
    Route a pilot message through the LLM orchestrator agent.

    Args:
        session_id: Unique pilot session identifier.
        message:    Raw (Whisper-transcribed) pilot message.
        db:         SQLAlchemy session for this request.

    Returns:
        dict with keys:
          - reply        (str)            : controller's reply text
          - dependency   (str)            : DEL | GND | TWR
          - registration (str | None)     : corrected callsign, or None
    """
    context: dict[str, Any] = {}
    agent = build_agent(session_id, db, context)

    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name=_APP_NAME,
        session_service=session_service,
    )

    user_content = Content(role="user", parts=[Part(text=message)])

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
        "reply": context.get("reply") or reply,
        "dependency": context.get("dependency", "DEL"),
        "registration": context.get("registration"),
    }
