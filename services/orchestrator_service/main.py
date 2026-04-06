import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import config
from db.connection import init_db
from api.flight_plans import router as flight_plans_router
from api.weather import router as weather_router
from api.clearances import router as clearances_router
from api.aircraft import router as aircraft_router
from api.dispatch import router as dispatch_router

LOG_LEVEL = os.environ.get("LOG_LEVEL", "info").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    logger.info("[orchestrator] DB tables ready | model: %s", os.environ.get("AGENT_MODEL", "<not set>"))
    yield
    logger.info("[orchestrator] shutting down")


app = FastAPI(
    title="AIrport Orchestrator",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(flight_plans_router)
app.include_router(weather_router)
app.include_router(clearances_router)
app.include_router(aircraft_router)
app.include_router(dispatch_router)


@app.get("/health")
async def health():
    return {"status": "ok", "model": os.environ.get("AGENT_MODEL", "<not set>")}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=True)
