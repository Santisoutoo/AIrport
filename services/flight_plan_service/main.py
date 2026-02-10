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
from core.database.connection import engine, Base
from core.database.models import FlightPlanModel

# Create database tables
Base.metadata.create_all(bind=engine)

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
