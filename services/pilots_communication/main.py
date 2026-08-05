import logging
import uuid

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from router import agent_name_to_url

from config import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Pilots Communication", version="0.1.0")


class ProcessResponse(BaseModel):
    agent: str
    transcription_raw: str
    transcription_corrected: str
    atc_response: str


@app.post("/process", response_model=ProcessResponse)
async def process(
    audio: UploadFile = File(...),
    agent: str = Form(...),
    session_id: str = Form(default=""),
):
    """Receive pilot audio + ATC agent name → transcribe → route to ATC agent → return response."""

    # 1. Determine agent
    try:
        agent_name, agent_url = agent_name_to_url(agent)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    session_id = session_id or str(uuid.uuid4())
    audio_bytes = await audio.read()
    filename = audio.filename or "audio.webm"

    async with httpx.AsyncClient(timeout=60.0) as client:
        # 2. Transcribe
        try:
            transcription_resp = await client.post(
                f"{config.TRANSCRIPTION_URL}/api/v1/transcription/transcribe",
                files={"audio": (filename, audio_bytes, audio.content_type or "audio/webm")},
            )
            transcription_resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Transcription service error: %s", exc)
            raise HTTPException(status_code=502, detail="Transcription service unavailable") from exc

        transcription = transcription_resp.json()
        raw = transcription.get("raw", "")
        corrected = transcription.get("corrected", raw)

        logger.info("[%s] raw=%r  corrected=%r", agent_name, raw, corrected)

        if not corrected:
            return ProcessResponse(
                agent=agent_name,
                transcription_raw=raw,
                transcription_corrected=corrected,
                atc_response="",
            )

        # 3. Send to ATC agent
        try:
            agent_resp = await client.post(
                f"{agent_url}/tasks/send",
                json={
                    "id": str(uuid.uuid4()),
                    "sessionId": session_id,
                    "message": {"role": "user", "parts": [{"text": corrected}]},
                },
            )
            agent_resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("%s agent error: %s", agent_name, exc)
            raise HTTPException(status_code=502, detail=f"{agent_name} agent unavailable") from exc

        atc_response = ""
        artifacts = agent_resp.json().get("artifacts", [])
        if artifacts:
            parts = artifacts[0].get("parts", [])
            if parts:
                atc_response = parts[0].get("text", "")

    return ProcessResponse(
        agent=agent_name,
        transcription_raw=raw,
        transcription_corrected=corrected,
        atc_response=atc_response,
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "pilots_communication"}
