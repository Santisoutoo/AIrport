"""REST endpoints to control the arrival scheduler."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.scheduler import get_scheduler

router = APIRouter()


class StartRequest(BaseModel):
    min_concurrent: int | None = Field(
        default=None,
        description="Minimum simultaneous arrivals to keep in the air. Defaults to ARRIVAL_MIN_CONCURRENT env (3).",
        ge=1,
    )


@router.get("/health")
async def health() -> dict:
    s = get_scheduler()
    return {
        "service": "arrival_simulator_service",
        "status": "healthy",
        "running": s.running,
        "min_concurrent": s.min_concurrent,
        "active_count": len(s.active),
    }


@router.post("/start")
async def start_arrivals(body: StartRequest | None = None) -> dict:
    s = get_scheduler()
    await s.start(min_concurrent=(body.min_concurrent if body else None))
    return {"running": s.running, "min_concurrent": s.min_concurrent}


@router.post("/restart")
async def restart_arrivals(body: StartRequest | None = None) -> dict:
    s = get_scheduler()
    await s.stop()
    await s.start(min_concurrent=(body.min_concurrent if body else None))
    return {"running": s.running, "min_concurrent": s.min_concurrent}


@router.post("/stop")
async def stop_arrivals() -> dict:
    s = get_scheduler()
    await s.stop()
    return {"running": s.running}


@router.get("/active")
async def active_arrivals() -> dict:
    s = get_scheduler()
    return {"active": s.active, "count": len(s.active)}
