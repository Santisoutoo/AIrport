from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router

app = FastAPI(
    title="Flight Plan Service",
    description="Generates flight plans for the AIrport ATC Simulator",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware for plugin access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api/v1/flight-plan", tags=["Flight Plan"])


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
