import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from runner import run_agent

LOG_LEVEL = os.environ.get("LOG_LEVEL", "info").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    model = os.environ.get("AGENT_MODEL", "<not set>")
    logger.info("[DEL] starting — model: %s", model)
    yield
    logger.info("[DEL] shutting down")


app = FastAPI(title="AIrport DEL Agent", version="0.2.0", lifespan=lifespan)


class RunRequest(BaseModel):
    session_id: str
    message: str
    flight_plan: dict[str, Any] | None = None
    atis: dict[str, Any] | None = None


class RunResponse(BaseModel):
    session_id: str
    reply: str
    clearance_data: dict[str, Any] | None = None


@app.post("/agents/delivery/run", response_model=RunResponse, tags=["delivery"])
async def run(req: RunRequest) -> RunResponse:
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        _executor, run_agent, req.session_id, req.message, req.flight_plan, req.atis
    )
    return RunResponse(
        session_id=req.session_id,
        reply=result["reply"],
        clearance_data=result.get("clearance_data"),
    )


@app.get("/agents/delivery/info", tags=["delivery"])
async def info():
    return {
        "name": "DEL",
        "model": os.environ.get("AGENT_MODEL", "<not set>"),
        "description": "ATC Delivery controller — issues IFR departure clearances",
    }


@app.get("/health")
async def health():
    return {"status": "ok", "model": os.environ.get("AGENT_MODEL", "<not set>")}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
