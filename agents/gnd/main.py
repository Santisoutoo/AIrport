from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from google.genai import types

from agent import build_runner
from config import config
from models import Artifact, ArtifactPart, TaskRequest, TaskResponse, TaskStatus

runner = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global runner
    runner = build_runner()
    print(f"[gnd_agent] mode={config.AGENT_MODE} model={config.get_litellm_model()}")
    yield


app = FastAPI(title="GND Agent", version="0.1.0", lifespan=lifespan)


# ---------- A2A endpoints ----------

@app.get("/.well-known/agent.json")
async def agent_card():
    return {
        "name": "GND",
        "description": "Ground controller — issues taxi clearances, pushback authorization, and runway crossings",
        "url": f"http://localhost:{config.PORT}",
        "version": "0.1.0",
        "capabilities": {"streaming": False},
    }


@app.post("/tasks/send", response_model=TaskResponse)
async def tasks_send(req: TaskRequest) -> TaskResponse:
    user_text = " ".join(p.text for p in req.message.parts)

    reply = ""
    try:
        content = types.Content(role="user", parts=[types.Part(text=user_text)])
        async for event in runner.run_async(
            user_id="default",
            session_id=req.sessionId,
            new_message=content,
        ):
            if event.is_final_response():
                if event.content and event.content.parts:
                    reply = event.content.parts[0].text
                break
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return TaskResponse(
        id=req.id,
        sessionId=req.sessionId,
        status=TaskStatus(state="completed"),
        artifacts=[Artifact(parts=[ArtifactPart(text=reply)])],
    )


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "GND", "mode": config.AGENT_MODE, "model": config.get_litellm_model()}
