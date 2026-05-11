import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router as arrivals_router
from core.scheduler import get_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

PREFIX = "/api/v1/arrivals"


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await get_scheduler().stop()


app = FastAPI(
    title="Arrival Simulator Service",
    description="Spawns AI arrival aircraft on the ILS and drives them to vacate.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(arrivals_router, prefix=PREFIX)


@app.get("/")
async def root() -> dict:
    return {
        "service": "Arrival Simulator Service",
        "version": "1.0.0",
        "docs": "/docs",
        "health": f"{PREFIX}/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
