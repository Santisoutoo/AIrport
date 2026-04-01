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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    print("[orchestrator] DB tables ready")
    yield
    print("[orchestrator] shutting down")


app = FastAPI(
    title="AIrport Orchestrator",
    version="0.1.0",
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
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=True)
