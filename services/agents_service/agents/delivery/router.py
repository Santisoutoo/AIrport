from fastapi import APIRouter
from pydantic import BaseModel

from agents.delivery.agent import DEL_AGENT, MODEL_STRING

router = APIRouter()


class RunRequest(BaseModel):
    session_id: str
    message: str


class RunResponse(BaseModel):
    session_id: str
    reply: str


@router.post("/run", response_model=RunResponse)
async def run(req: RunRequest) -> RunResponse:
    """Send a message to the DEL agent and receive a reply."""
    return RunResponse(session_id=req.session_id, reply="[DEL stub]")


@router.get("/info")
async def info():
    """Return metadata about the DEL agent."""
    return {
        "name": DEL_AGENT.name,
        "model": MODEL_STRING,
        "tools": [t.__name__ if callable(t) else str(t) for t in DEL_AGENT.tools],
    }
