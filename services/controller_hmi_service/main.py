from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import router

PREFIX = "/api/v1/hmi"

app = FastAPI(
    title="Controller HMI Service",
    description="Electronic Flight Strip and weather display for ATC controllers",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes (proxy endpoints)
app.include_router(router, prefix=PREFIX, tags=["HMI"])

# Serve static frontend files -- mount AFTER API routes so /api/* takes precedence
app.mount("/", StaticFiles(directory="static", html=True), name="static")


@app.get("/api")
async def api_root():
    """API root endpoint with service info"""
    return {
        "service": "Controller HMI Service",
        "version": "1.0.0",
        "docs": "/docs",
        "health": f"{PREFIX}/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
