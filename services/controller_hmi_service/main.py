import os
from pathlib import Path


def _load_env_file():
    """Load .env from the project root (two levels up) if env vars are missing."""
    env_path = Path(__file__).parent.parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()


_load_env_file()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from api.routes import router
from api.plugin_routes import router as plugin_router

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

# API routes
app.include_router(router, prefix=PREFIX, tags=["HMI"])
app.include_router(plugin_router)


@app.get("/setup", include_in_schema=False)
async def setup_page():
    return FileResponse("static/setup.html")


# Generate config.js into the static dir so StaticFiles serves it.
_static_dir = Path(__file__).resolve().parent / "static"
_asr_url = os.getenv("ASR_URL", "")
_orchestrator_url = os.getenv("ORCHESTRATOR_URL", "http://localhost:8007")
(_static_dir / "config.js").write_text(
    f"window.HMI_CONFIG = {{\n"
    f'  ASR_URL: "{_asr_url}",\n'
    f'  ORCHESTRATOR_URL: "{_orchestrator_url}"\n'
    f"}};\n",
    encoding="utf-8",
)

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
