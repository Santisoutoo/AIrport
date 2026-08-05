"""Generic ADK runner shared by the DEL / GND / TWR pilot agents.

Every pilot agent used to ship its own ~85-line ``run_agent`` that differed only in
four things: the ADK ``Agent`` object, the ADK app name, which context blocks the
orchestrator attaches to the transmission, and the JSON keys the agent's prompt
promises to emit. Everything else -- session handling, the ``run_async`` event loop,
the regex JSON extraction, the error path and the log lines -- was identical.

``build_run_agent()`` is that common body; each agent's ``runner.py`` supplies the
configuration and re-exports a thin wrapper with its own public signature.

Packaging note
--------------
This file is the single source of truth, but it is **vendored** into
``agents/<phase>/shared/agent_runner.py`` because each agent is deployed with
``gcloud run deploy --source agents/<phase>``: the Docker build context is the agent
directory itself (``COPY . .``), so nothing above it can be imported at runtime. That
is the same convention ``shared/callbacks.py`` already follows. Run
``python scripts/sync_agent_common.py`` after editing this file;
``tests/unit/agents/test_agent_common_vendoring.py`` fails if the copies drift.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

# Every agent runs its ADK session under the same synthetic user.
_USER_ID = "pilot"

# The prompts instruct the model to emit a single JSON object; it is usually
# wrapped in prose or a markdown fence, hence the greedy DOTALL match.
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True)
class ContextField:
    """One optional context block the orchestrator may attach to a request.

    ``name`` is the keyword argument the agent's ``run_agent`` accepts;
    ``template`` is the line rendered into the ``[CONTEXT]`` section, with
    ``{value}`` standing for the value itself.
    """

    name: str
    template: str


@dataclass(frozen=True)
class AgentRunnerConfig:
    """Everything that differs between the DEL, GND and TWR runners."""

    label: str
    """Short position name used in every log line, e.g. ``"DEL"``."""

    app_name: str
    """ADK application name, e.g. ``"airport_del"``."""

    text_key: str
    """JSON key holding the readback text, e.g. ``"clearance_text"``."""

    data_key: str
    """JSON key holding the structured payload, e.g. ``"clearance_data"``.

    It is also the second key of the returned dict, so it is part of the
    HTTP contract the orchestrator consumes.
    """

    context_fields: tuple[ContextField, ...] = ()
    """Context blocks appended to the transmission, in render order."""

    context_header: str = "\n\n[CONTEXT]"
    """Header line that opens the context section."""


def build_agent_context(message: str, config: AgentRunnerConfig, values: dict[str, Any]) -> str:
    """Append the non-empty context blocks to ``message``.

    Returns ``message`` untouched when the orchestrator attached no context.
    """
    present = [(f, values.get(f.name)) for f in config.context_fields]
    present = [(f, value) for f, value in present if value]
    if not present:
        return message

    parts = [message, config.context_header]
    parts.extend(f.template.format(value=value) for f, value in present)
    return "\n".join(parts)


def build_run_agent(
    agent: Any,
    config: AgentRunnerConfig,
    logger: logging.Logger | None = None,
) -> Callable[..., dict[str, Any]]:
    """Build the ``run_agent`` callable for one pilot agent.

    The returned function takes ``(session_id, message, **context)`` where the
    accepted context keywords are ``config.context_fields``. It always returns
    ``{"reply": <text>, config.data_key: <dict | None>}`` -- including on failure,
    so the FastAPI layer never has to special-case errors.
    """
    log = logger if logger is not None else logging.getLogger(__name__)

    session_service = InMemorySessionService()
    adk_runner = Runner(agent=agent, app_name=config.app_name, session_service=session_service)

    def run_agent(session_id: str, message: str, **context: Any) -> dict[str, Any]:
        # Enrich the message with context pre-fetched by the orchestrator
        enriched = build_agent_context(message, config, context)

        log.info("[%s] run_agent | session=%s | msg=%r", config.label, session_id, enriched[:200])

        async def _run() -> str:
            existing = await session_service.get_session(
                app_name=config.app_name, user_id=_USER_ID, session_id=session_id
            )
            if not existing:
                await session_service.create_session(app_name=config.app_name, user_id=_USER_ID, session_id=session_id)
            reply_parts = []
            async for event in adk_runner.run_async(
                user_id=_USER_ID,
                session_id=session_id,
                new_message=Content(role="user", parts=[Part(text=enriched)]),
            ):
                log.debug("[%s] event: %s", config.label, event)
                if event.is_final_response() and event.content:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            reply_parts.append(part.text)
            return "".join(reply_parts).strip()

        try:
            raw_reply = asyncio.run(_run())
        except Exception:
            log.exception("[%s] agent error", config.label)
            return {"reply": f"[{config.label} error] agent failed", config.data_key: None}

        log.info("[%s] raw reply: %r", config.label, raw_reply[:300])

        # Extract structured data from the JSON the agent is instructed to output
        reply_text = raw_reply
        reply_data = None
        try:
            match = _JSON_BLOCK.search(raw_reply)
            if match:
                parsed = json.loads(match.group())
                reply_text = parsed.get(config.text_key, raw_reply)
                reply_data = parsed.get(config.data_key)
        except Exception as exc:
            log.warning("[%s] could not parse JSON from reply: %s", config.label, exc)

        log.info(
            "[%s] result | %s=%r | %s=%s",
            config.label,
            config.text_key,
            reply_text[:80],
            config.data_key,
            reply_data,
        )
        return {"reply": reply_text, config.data_key: reply_data}

    return run_agent
