import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from agents.delivery.agent import DEL_AGENT, MODEL_STRING
from runner import run_del_agent

logger = logging.getLogger(__name__)

router = APIRouter()

_executor = ThreadPoolExecutor(max_workers=4)


class RunRequest(BaseModel):
    session_id: str
    message: str
    flight_plan: dict[str, Any] | None = None
    atis: dict[str, Any] | None = None


class RunResponse(BaseModel):
    session_id: str
    reply: str
    clearance_data: dict[str, Any] | None = None


@router.post("/run", response_model=RunResponse)
async def run(req: RunRequest) -> RunResponse:
    """Send a pilot message to the DEL agent and receive an IFR clearance reply."""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        _executor,
        run_del_agent,
        req.session_id,
        req.message,
        req.flight_plan,
        req.atis,
    )
    return RunResponse(
        session_id=req.session_id,
        reply=result["reply"],
        clearance_data=result["clearance_data"],
    )


@router.get("/info")
async def info():
    """Return metadata about the DEL agent."""
    return {
        "name": DEL_AGENT.name,
        "model": MODEL_STRING,
        "tools": [t.__name__ if callable(t) else str(t) for t in DEL_AGENT.tools],
    }
