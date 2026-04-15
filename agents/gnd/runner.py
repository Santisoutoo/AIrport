import asyncio
import json
import logging
import re
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from agent.agent import gnd_agent

logger = logging.getLogger(__name__)

_APP_NAME = "airport_gnd"
_session_service = InMemorySessionService()
_runner = Runner(agent=gnd_agent, app_name=_APP_NAME, session_service=_session_service)


def run_agent(
    session_id: str,
    message: str,
    clearance_data: dict | None = None,
) -> dict[str, Any]:
    # Enrich message with pre-fetched clearance context from the orchestrator
    enriched = message
    if clearance_data:
        enriched = "\n".join([message, "\n[CONTEXT]", f"Clearance data: {clearance_data}"])

    logger.info("[GND] run_agent | session=%s | msg=%r", session_id, enriched[:200])

    async def _run() -> str:
        existing = await _session_service.get_session(
            app_name=_APP_NAME, user_id="pilot", session_id=session_id
        )
        if not existing:
            await _session_service.create_session(
                app_name=_APP_NAME, user_id="pilot", session_id=session_id
            )
        reply_parts = []
        async for event in _runner.run_async(
            user_id="pilot",
            session_id=session_id,
            new_message=Content(role="user", parts=[Part(text=enriched)]),
        ):
            logger.debug("[GND] event: %s", event)
            if event.is_final_response() and event.content:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        reply_parts.append(part.text)
        return "".join(reply_parts).strip()

    try:
        raw_reply = asyncio.run(_run())
    except Exception:
        logger.exception("[GND] agent error")
        return {"reply": "[GND error] agent failed", "taxi_data": None}

    logger.info("[GND] raw reply: %r", raw_reply[:300])

    # Extract structured data from the JSON the agent is instructed to output
    instruction_text = raw_reply
    taxi_data = None
    try:
        match = re.search(r"\{.*\}", raw_reply, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            instruction_text = parsed.get("instruction_text", raw_reply)
            taxi_data = parsed.get("taxi_data")
    except Exception as exc:
        logger.warning("[GND] could not parse JSON from reply: %s", exc)

    logger.info(
        "[GND] result | instruction_text=%r | taxi_data=%s",
        instruction_text[:80],
        taxi_data,
    )
    return {"reply": instruction_text, "taxi_data": taxi_data}
