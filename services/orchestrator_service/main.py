import logging
import os
from contextlib import asynccontextmanager

from api.aircraft import router as aircraft_router
from api.arrivals import router as arrivals_router
from api.clearances import router as clearances_router
from api.debrief import router as debrief_router
from api.dispatch import router as dispatch_router
from api.events_subscriber import start_subscriber, stop_subscriber
from api.flight_plans import router as flight_plans_router
from api.weather import router as weather_router
from db.connection import init_db
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import config

LOG_LEVEL = os.environ.get("LOG_LEVEL", "info").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    logger.info("[orchestrator] DB tables ready | model: %s", os.environ.get("AGENT_MODEL", "<not set>"))
    await start_subscriber()
    yield
    await stop_subscriber()
    logger.info("[orchestrator] shutting down")


app = FastAPI(
    title="AIrport Orchestrator",
    version="0.2.0",
    lifespan=lifespan,
)

_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:8005").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(flight_plans_router)
app.include_router(weather_router)
app.include_router(clearances_router)
app.include_router(aircraft_router)
app.include_router(dispatch_router)
app.include_router(debrief_router)
app.include_router(arrivals_router)


@app.get("/health")
async def health():
    return {"status": "ok", "model": os.environ.get("AGENT_MODEL", "<not set>")}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=True)
