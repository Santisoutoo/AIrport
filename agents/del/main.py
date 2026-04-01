import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from config import config
from runner import run_agent

_executor = ThreadPoolExecutor(max_workers=4)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    print(f"[del] starting — model: {config.get_litellm_model()}")
    yield
    print("[del] shutting down")


app = FastAPI(title="AIrport DEL Agent", version="0.1.0", lifespan=lifespan)


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
    return {"name": "DEL", "description": "ATC Delivery controller — issues IFR departure clearances"}


@app.get("/health")
async def health():
    return {"status": "ok", "model": config.get_litellm_model()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=True)
