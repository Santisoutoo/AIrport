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
    logger.info("[GND] starting — model: %s", model)
    yield
    logger.info("[GND] shutting down")


app = FastAPI(title="AIrport GND Agent", version="0.1.0", lifespan=lifespan)


class RunRequest(BaseModel):
    session_id: str
    message: str
    clearance_data: dict[str, Any] | None = None


class RunResponse(BaseModel):
    session_id: str
    reply: str
    taxi_data: dict[str, Any] | None = None


@app.post("/agents/ground/run", response_model=RunResponse, tags=["ground"])
async def run(req: RunRequest) -> RunResponse:
    logger.info(
        "[GND] ▶ request | session=%s | msg=%r | clearance_data=%s",
        req.session_id, req.message[:80], bool(req.clearance_data),
    )
    t0 = asyncio.get_event_loop().time()
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            _executor, run_agent, req.session_id, req.message, req.clearance_data
        )
    except Exception:
        logger.exception("[GND] ✗ executor error | session=%s", req.session_id)
        raise
    elapsed_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
    logger.info(
        "[GND] ■ done | session=%s | reply=%r | taxi_data=%s | %d ms",
        req.session_id, result["reply"][:80], bool(result.get("taxi_data")), elapsed_ms,
    )
    return RunResponse(
        session_id=req.session_id,
        reply=result["reply"],
        taxi_data=result.get("taxi_data"),
    )


@app.get("/agents/ground/info", tags=["ground"])
async def info():
    return {
        "name": "GND",
        "model": os.environ.get("AGENT_MODEL", "<not set>"),
        "description": "ATC Ground controller — issues pushback and taxi instructions",
    }


@app.get("/health")
async def health():
    return {"status": "ok", "model": os.environ.get("AGENT_MODEL", "<not set>")}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
