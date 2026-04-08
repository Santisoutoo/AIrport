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
    logger.info("[TWR] starting — model: %s", model)
    yield
    logger.info("[TWR] shutting down")


app = FastAPI(title="AIrport TWR Agent", version="0.1.0", lifespan=lifespan)


class RunRequest(BaseModel):
    session_id: str
    message: str
    clearance_data: dict[str, Any] | None = None


class RunResponse(BaseModel):
    session_id: str
    reply: str
    reply_data: dict[str, Any] | None = None


@app.post("/agents/tower/run", response_model=RunResponse, tags=["tower"])
async def run(req: RunRequest) -> RunResponse:
    logger.info(
        "[TWR] ▶ request | session=%s | msg=%r | clearance_data=%s",
        req.session_id, req.message[:80], bool(req.clearance_data),
    )
    t0 = asyncio.get_event_loop().time()
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            _executor, run_agent, req.session_id, req.message, req.clearance_data
        )
    except Exception:
        logger.exception("[TWR] ✗ executor error | session=%s", req.session_id)
        raise
    elapsed_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
    logger.info(
        "[TWR] ■ done | session=%s | reply=%r | reply_data=%s | %d ms",
        req.session_id, result["reply"][:80], bool(result.get("reply_data")), elapsed_ms,
    )
    return RunResponse(
        session_id=req.session_id,
        reply=result["reply"],
        reply_data=result.get("reply_data"),
    )


@app.get("/agents/tower/info", tags=["tower"])
async def info():
    return {
        "name": "TWR",
        "model": os.environ.get("AGENT_MODEL", "<not set>"),
        "description": "Pilot on Tower frequency — reads back lineup, takeoff and landing clearances",
    }


@app.get("/health")
async def health():
    return {"status": "ok", "model": os.environ.get("AGENT_MODEL", "<not set>")}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8082"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
