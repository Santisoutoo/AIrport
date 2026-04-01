import asyncio
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from agent.agent import build_agent

_APP_NAME = "airport_del"


def run_agent(
    session_id: str,
    message: str,
    flight_plan: dict | None = None,
    atis: dict | None = None,
) -> dict[str, Any]:
    """
    Send a pilot message to the DEL agent and return the clearance reply
    plus any structured clearance data to be persisted by the orchestrator.

    Always called from a ThreadPoolExecutor thread (never from the async
    event loop), so asyncio.run() is safe here.
    """
    context: dict[str, Any] = {}
    agent = build_agent(flight_plan, atis, context)

    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name=_APP_NAME, session_service=session_service)
    user_content = Content(role="user", parts=[Part(text=message)])

    async def _run() -> str:
        await session_service.create_session(
            app_name=_APP_NAME, user_id="pilot", session_id=session_id
        )
        reply_parts = []
        async for event in runner.run_async(
            user_id="pilot", session_id=session_id, new_message=user_content
        ):
            if event.is_final_response() and event.content:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        reply_parts.append(part.text)
        return " ".join(reply_parts).strip()

    try:
        reply = asyncio.run(_run())
    except Exception as exc:
        reply = f"[DEL error] {exc}"

    return {"reply": reply, "clearance_data": context.get("clearance_data")}
