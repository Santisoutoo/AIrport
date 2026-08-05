import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import (
    api_generator,
    health_router,
    api_generation_router,
    local_generation_router,
    plans_router,
    reference_router,
)
from sqlalchemy import inspect, text

from core.database.connection import engine, Base
from core.database.models import FlightPlanModel

# Create database tables
Base.metadata.create_all(bind=engine)

# Add callsign column if missing (no Alembic — manual migration)
with engine.connect() as conn:
    columns = [c["name"] for c in inspect(engine).get_columns("flight_plans")]
    if "callsign" not in columns:
        conn.execute(text("ALTER TABLE flight_plans ADD COLUMN callsign VARCHAR(10)"))
        conn.commit()

PREFIX = "/api/v1/flight-plan"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await api_generator.close()


app = FastAPI(
    title="Flight Plan Service",
    description="Generates flight plans for the AIrport ATC Simulator",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
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

# Include API routes
app.include_router(health_router, prefix=PREFIX)
app.include_router(api_generation_router, prefix=PREFIX)
app.include_router(local_generation_router, prefix=PREFIX)
app.include_router(plans_router, prefix=PREFIX)
app.include_router(reference_router, prefix=PREFIX)


@app.get("/")
async def root():
    """Root endpoint with service info"""
    return {
        "service": "Flight Plan Service",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/flight-plan/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
