import asyncio
import json
import logging
import os
import re
from typing import Any

import redis as redis_lib
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from agent.agent import del_agent

logger = logging.getLogger(__name__)

_APP_NAME = "airport_del"

_REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
_REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
_AIRPORT_ICAO_KEY = "airport:current:icao"


def _get_airport_icao() -> str | None:
    """Fetch the active airport ICAO code from Redis."""
    try:
        r = redis_lib.Redis(host=_REDIS_HOST, port=_REDIS_PORT, db=0, decode_responses=True)
        return r.get(_AIRPORT_ICAO_KEY)
    except Exception:
        logger.warning("[DEL] could not read airport ICAO from Redis")
        return None


def run_agent(
    session_id: str,
    message: str,
    flight_plan: dict | None = None,
    atis: dict | None = None,
) -> dict[str, Any]:
    # Enrich message with pre-fetched context from the orchestrator
    airport_icao = _get_airport_icao()
    enriched = message
    if flight_plan or atis or airport_icao:
        parts = [message, "\n\n[CONTEXT]"]
        if airport_icao:
            parts.append(f"Airport ICAO: {airport_icao}")
        if flight_plan:
            parts.append(f"Flight plan: {flight_plan}")
        if atis:
            parts.append(f"ATIS: {atis}")
        enriched = "\n".join(parts)

    logger.info("[DEL] run_agent | session=%s | msg=%r", session_id, enriched[:200])

    session_service = InMemorySessionService()
    runner = Runner(agent=del_agent, app_name=_APP_NAME, session_service=session_service)

    async def _run() -> str:
        await session_service.create_session(
            app_name=_APP_NAME, user_id="pilot", session_id=session_id
        )
        reply_parts = []
        async for event in runner.run_async(
            user_id="pilot",
            session_id=session_id,
            new_message=Content(role="user", parts=[Part(text=enriched)]),
        ):
            logger.debug("[DEL] event: %s", event)
            if event.is_final_response() and event.content:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        reply_parts.append(part.text)
        return "".join(reply_parts).strip()

    try:
        raw_reply = asyncio.run(_run())
    except Exception:
        logger.exception("[DEL] agent error")
        return {"reply": "[DEL error] agent failed", "clearance_data": None}

    logger.info("[DEL] raw reply: %r", raw_reply[:300])

    # Extract structured data from the JSON the agent is instructed to output
    clearance_text = raw_reply
    clearance_data = None
    try:
        match = re.search(r"\{.*\}", raw_reply, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            clearance_text = parsed.get("clearance_text", raw_reply)
            clearance_data = parsed.get("clearance_data")
    except Exception as exc:
        logger.warning("[DEL] could not parse JSON from reply: %s", exc)

    logger.info(
        "[DEL] result | clearance_text=%r | clearance_data=%s",
        clearance_text[:80],
        clearance_data,
    )
    return {"reply": clearance_text, "clearance_data": clearance_data}
