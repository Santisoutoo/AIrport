"""Generic FastAPI wrapper shared by the DEL / GND / TWR pilot agents.

The three ``main.py`` files were the same ~90-line app: a ``POST /agents/<role>/run``
handler that hands ``run_agent`` to a four-worker ``ThreadPoolExecutor`` (the runner
opens its own event loop with ``asyncio.run()``, so it cannot run inside FastAPI's),
plus ``GET /agents/<role>/info`` and ``GET /health``. Only the position label, the
route, the request/response field names and the OpenAPI metadata differed.

``create_app()`` is that common body; each agent's ``main.py`` supplies the
configuration and keeps only its ``uvicorn`` entry point.

Note this module deliberately does **not** use ``from __future__ import annotations``:
the request and response models are created per-app inside ``create_app()``, so the
handler annotations must be real objects when FastAPI inspects them, not strings it
would try to resolve against module globals.

Packaging note
--------------
Same as ``agent_runner.py``: this file is the single source of truth and is vendored
into ``agents/<phase>/shared/agent_app.py`` because each agent's Docker build context
is its own directory. Run ``python scripts/sync_agent_common.py`` after editing.
"""

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Callable, Optional

from fastapi import FastAPI
from pydantic import create_model

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s — %(message)s"

# Requests are served by run_agent() on a worker thread because run_agent opens
# its own event loop; four workers matches the original per-agent setting.
_MAX_WORKERS = 4


@dataclass(frozen=True)
class AgentAppConfig:
    """Everything that differs between the DEL, GND and TWR FastAPI apps."""

    label: str
    """Short position name used in every log line, e.g. ``"DEL"``."""

    role: str
    """URL segment and OpenAPI tag, e.g. ``"delivery"`` -> ``/agents/delivery/run``."""

    title: str
    """OpenAPI title, e.g. ``"AIrport DEL Agent"``."""

    version: str
    """OpenAPI version string."""

    description: str
    """Human-readable blurb returned by ``GET /agents/<role>/info``."""

    data_key: str
    """Structured-payload key of the JSON response, e.g. ``"clearance_data"``.

    This is part of the contract the orchestrator consumes -- do not rename it.
    """

    context_fields: tuple[str, ...] = ()
    """Optional context fields accepted in the request body, in payload order."""


def configure_logging() -> None:
    """Apply the agents' shared logging configuration from ``LOG_LEVEL``."""
    level = os.environ.get("LOG_LEVEL", "info").upper()
    logging.basicConfig(level=level, format=_LOG_FORMAT)


def create_app(
    config: AgentAppConfig,
    run_agent: Callable[..., dict],
    logger: Optional[logging.Logger] = None,
) -> FastAPI:
    """Build the FastAPI app for one pilot agent."""
    configure_logging()
    log = logger if logger is not None else logging.getLogger(__name__)

    executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS)

    optional_dict = (Optional[dict[str, Any]], None)
    RunRequest = create_model(
        "RunRequest",
        session_id=(str, ...),
        message=(str, ...),
        **{name: optional_dict for name in config.context_fields},
    )
    RunResponse = create_model(
        "RunResponse",
        session_id=(str, ...),
        reply=(str, ...),
        **{config.data_key: optional_dict},
    )

    # Pre-render the variable part of the two per-request log lines so the
    # emitted text is identical to the hand-written per-agent versions.
    request_fmt = "[%s] ▶ request | session=%s | msg=%r" + "".join(
        f" | {name}=%s" for name in config.context_fields
    )
    done_fmt = f"[%s] ■ done | session=%s | reply=%r | {config.data_key}=%s | %d ms"

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        model = os.environ.get("AGENT_MODEL", "<not set>")
        log.info("[%s] starting — model: %s", config.label, model)
        yield
        log.info("[%s] shutting down", config.label)

    app = FastAPI(title=config.title, version=config.version, lifespan=lifespan)

    @app.post(f"/agents/{config.role}/run", response_model=RunResponse, tags=[config.role])
    async def run(req: RunRequest) -> RunResponse:
        context = [getattr(req, name) for name in config.context_fields]
        log.info(
            request_fmt,
            config.label, req.session_id, req.message[:80], *[bool(v) for v in context],
        )
        t0 = asyncio.get_event_loop().time()
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                executor, run_agent, req.session_id, req.message, *context
            )
        except Exception:
            log.exception("[%s] ✗ executor error | session=%s", config.label, req.session_id)
            raise
        elapsed_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
        log.info(
            done_fmt,
            config.label, req.session_id, result["reply"][:80],
            bool(result.get(config.data_key)), elapsed_ms,
        )
        return RunResponse(
            session_id=req.session_id,
            reply=result["reply"],
            **{config.data_key: result.get(config.data_key)},
        )

    @app.get(f"/agents/{config.role}/info", tags=[config.role])
    async def info():
        return {
            "name": config.label,
            "model": os.environ.get("AGENT_MODEL", "<not set>"),
            "description": config.description,
        }

    @app.get("/health")
    async def health():
        return {"status": "ok", "model": os.environ.get("AGENT_MODEL", "<not set>")}

    return app
