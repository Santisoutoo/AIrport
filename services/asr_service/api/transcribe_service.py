import io

import httpx
from fastapi import HTTPException

_ATC_PROMPT = (
    "ATC radio communication. Phonetic alphabet: Alpha Bravo Charlie Delta Echo Foxtrot "
    "Golf Hotel India Juliet Kilo Lima Mike November Oscar Papa Quebec Romeo Sierra Tango "
    "Uniform Victor Whiskey X-ray Yankee Zulu. "
    "Common ATC words: runway, taxiway, squawk, heading, altitude, frequency, cleared, "
    "contact, hold short, line up, wind, knots, feet, QNH, SID, ILS, VOR, DME."
)

# Maps spoken phonetic words to their ICAO letter (uppercase)
_PHONETIC_MAP = {
    "alpha": "A", "alfa": "A",
    "bravo": "B",
    "charlie": "C",
    "delta": "D",
    "echo": "E",
    "foxtrot": "F",
    "golf": "G",
    "hotel": "H",
    "india": "I",
    "juliet": "J",
    "kilo": "K",
    "lima": "L",
    "mike": "M",
    "november": "N",
    "oscar": "O",
    "papa": "P",
    "quebec": "Q",
    "romeo": "R",
    "sierra": "S",
    "tango": "T",
    "uniform": "U",
    "victor": "V",
    "whiskey": "W",
    "x-ray": "X", "xray": "X",
    "yankee": "Y",
    "zulu": "Z",
}


def _normalize_phonetic(text: str) -> str:
    """Replace isolated phonetic words with their ICAO letter."""
    import re
    pattern = re.compile(
        r'\b(' + '|'.join(re.escape(k) for k in _PHONETIC_MAP) + r')\b',
        re.IGNORECASE,
    )
    return pattern.sub(lambda m: _PHONETIC_MAP[m.group(0).lower()], text)



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
        async with httpx.AsyncClient(timeout=30.0) as client:
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
    """Transcribe audio using an OpenAI-compatible API key endpoint."""
    if not api_key:
        raise HTTPException(status_code=400, detail="API key not configured")
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key, base_url=base_url)

        # gpt-4o-transcribe / gpt-4o-mini-transcribe only support json format
        # and do not accept a prompt parameter
        _gpt4o_models = {"gpt-4o-transcribe", "gpt-4o-mini-transcribe",
                         "gpt-4o-mini-transcribe-2025-12-15", "gpt-4o-transcribe-diarize"}
        if model in _gpt4o_models:
            result = await client.audio.transcriptions.create(
                model=model,
                file=(filename, io.BytesIO(audio_bytes), content_type),
                response_format="json",
            )
        else:
            # whisper-1: supports prompt and verbose_json
            result = await client.audio.transcriptions.create(
                model=model,
                file=(filename, io.BytesIO(audio_bytes), content_type),
                language="en",
                prompt=_ATC_PROMPT,
            )
        return _normalize_phonetic(result.text)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"API transcription error: {exc}",
        ) from exc
