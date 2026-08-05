import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from core.database.connection import engine, Base
from core.database.models import ATISModel
from core.metar_taf_fetcher import close_client

# Create database tables
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Release the shared httpx client used for METAR/TAF on shutdown."""
    yield
    await close_client()


app = FastAPI(
    title="Weather Service",
    description="Weather and ATIS service for the AIrport ATC Simulator",
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
app.include_router(router, prefix="/api/v1/weather", tags=["Weather"])


@app.get("/")
async def root():
    """Root endpoint with service info"""
    return {
        "service": "Weather Service",
        "version": "1.0.0",
        "description": "ATIS, METAR, and TAF data for AIrport ATC Simulator",
        "docs": "/docs",
        "health": "/api/v1/weather/health",
        "endpoints": {
            "atis": "/api/v1/weather/atis/{icao_code}",
            "metar": "/api/v1/weather/metar/{icao_code}",
            "taf": "/api/v1/weather/taf/{icao_code}",
            "airports": "/api/v1/weather/airports",
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
