import io

import httpx
from fastapi import HTTPException

from ..core import settings
from ..core.phonetics import normalize_phonetic
from ..core.corrections import correct_callsigns
from ..prompts.whisper_context import ATC_PROMPT

_GPT4O_MODELS = {
    "gpt-4o-transcribe",
    "gpt-4o-mini-transcribe",
    "gpt-4o-mini-transcribe-2025-12-15",
    "gpt-4o-transcribe-diarize",
}


async def via_ollama(
    audio_bytes: bytes,
    filename: str,
    content_type: str,
    *,
    model: str,
    ollama_url: str,
) -> str:
    """Transcribe audio using Ollama's OpenAI-compatible endpoint."""
    try:
        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT) as client:
            resp = await client.post(
                f"{ollama_url}/v1/audio/transcriptions",
                files={"file": (filename, audio_bytes, content_type)},
                data={"model": model},
            )
            resp.raise_for_status()
            return resp.json().get("text", "")
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Ollama transcription error: {exc}",
        ) from exc


async def via_api(
    audio_bytes: bytes,
    filename: str,
    content_type: str,
    *,
    model: str,
    api_key: str,
    base_url: str,
) -> str:
    """Transcribe audio using an OpenAI-compatible API endpoint."""
    if not api_key:
        raise HTTPException(status_code=400, detail="API key not configured")
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key, base_url=base_url)

        if model in _GPT4O_MODELS:
            result = await client.audio.transcriptions.create(
                model=model,
                file=(filename, io.BytesIO(audio_bytes), content_type),
                response_format="json",
                language=settings.WHISPER_LANGUAGE,
            )
        else:
            result = await client.audio.transcriptions.create(
                model=model,
                file=(filename, io.BytesIO(audio_bytes), content_type),
                language=settings.WHISPER_LANGUAGE,
                prompt=ATC_PROMPT,
            )
        return correct_callsigns(normalize_phonetic(result.text))
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"API transcription error: {exc}",
        ) from exc
