# ASR Service

**Port 8006:8000** · [`services/asr_service/`](../../services/asr_service/) · speech-to-text for
controller transmissions. Health: `/api/v1/asr/health`. See [architecture](../architecture.md).

## Responsibility

Transcribe controller mic audio with a **Whisper model fine-tuned for ATC** (faster-whisper), then
**correct the callsign** using phonetics + an LLM corrector, and hand the clean transcript to the
[orchestrator](orchestrator_service.md) (`ORCHESTRATOR_URL`). Uses Redis and Gemini (Vertex AI)
for the corrector (`ASR_LLM_MODEL`, default `gemini-3-flash-preview`).

## Layout

| Path | Role |
|---|---|
| [`main.py`](../../services/asr_service/main.py) | FastAPI entrypoint |
| [`api/routes.py`](../../services/asr_service/api/routes.py) | ASR endpoints (transcribe) |
| [`api/transcribe_service.py`](../../services/asr_service/api/transcribe_service.py) | Transcription orchestration |
| [`api/config_service.py`](../../services/asr_service/api/config_service.py) | Runtime config endpoints |
| [`core/corrections.py`](../../services/asr_service/core/corrections.py) | Callsign correction logic |
| [`core/phonetics.py`](../../services/asr_service/core/phonetics.py) | ICAO phonetic alphabet handling |
| [`core/config.py`](../../services/asr_service/core/config.py), [`core/settings.py`](../../services/asr_service/core/settings.py) | Model / service settings |
| [`prompts/whisper_context.py`](../../services/asr_service/prompts/whisper_context.py) | Whisper initial-prompt / context biasing |
| [`prompts/llm_corrector.py`](../../services/asr_service/prompts/llm_corrector.py) | LLM corrector prompt |
| [`download_model.py`](../../services/asr_service/download_model.py) | Fetches the Whisper ATC model into the `asr_hf_cache` volume (~1.5 GB on first run) |

> Related standalone module: [`transcription/`](../../transcription/) is a separate ASR module
> (Whisper + callsign correction + phonetics) with its own Dockerfile — an alternate/earlier
> packaging of the same capability.

## Evaluation

WER is measured with `jiwer` via [`agents_evaluation/evaluate_wer.py`](../../agents_evaluation/evaluate_wer.py)
against the phase corpora. See [data-and-testing](../data-and-testing.md).

## Related
[architecture](../architecture.md) · [orchestrator](orchestrator_service.md) · [controller_hmi](controller_hmi_service.md) · [data-and-testing](../data-and-testing.md)
