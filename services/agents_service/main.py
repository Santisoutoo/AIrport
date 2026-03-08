from contextlib import asynccontextmanager
from fastapi import FastAPI
from config import config
from agents.delivery.router import router as delivery_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(
        f"[agents_service] starting in {config.AGENT_MODE} mode — model: {config.get_litellm_model()}")
    yield
    print("[agents_service] shutting down")


app = FastAPI(
    title="AIrport Agents Service",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(
    delivery_router, prefix="/agents/delivery", tags=["delivery"])


@app.get("/health")
async def health():
    return {"status": "ok", "mode": config.AGENT_MODE, "model": config.get_litellm_model()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=True)
