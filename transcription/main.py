import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from api.transcribe_service import load_model
from config import get_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_config()
    logger.info(
        "[transcription] starting — whisper=%s  llm=%s",
        cfg.HF_MODEL,
        cfg.get_litellm_model(),
    )
    load_model()
    yield
    logger.info("[transcription] shutting down.")


app = FastAPI(
    title="Transcription Service",
    description="Whisper ASR + LLM correction for AIrport ATC",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
