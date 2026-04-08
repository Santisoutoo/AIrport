import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from api.transcribe_service import load_model
from core.config import get_settings


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_settings()
    logger.info("ASR Service starting — model: %s", cfg.hf_model)
    load_model()
    yield
    logger.info("ASR Service shutting down.")


app = FastAPI(
    title="ASR Service",
    description="Automatic Speech Recognition for AIrport ATC Simulator",
    version="2.0.0",
    docs_url="/docs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    cfg = get_settings()
    uvicorn.run(app, host="0.0.0.0", port=cfg.port, log_level=cfg.log_level)
