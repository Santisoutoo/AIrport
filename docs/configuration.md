# Configuration Reference

Every variable defined in [`.env.example`](../.env.example), grouped by subsystem.

## Service URLs

| Variable | Default | Description |
|---|---|---|
| `ORCHESTRATOR_URL` | `http://orchestrator_service:8006` | Orchestrator base URL (internal container port) |
| `ASR_URL` | `http://asr_service:8000/api/v1/asr` | ASR endpoint URL |

## PostgreSQL

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_HOST` | `postgres` | DB host (docker service name) |
| `POSTGRES_PORT` | `5432` | DB port |
| `POSTGRES_DB` | `airport` | Database name |
| `POSTGRES_USER` | `airport_user` | DB user |
| `POSTGRES_PASSWORD` | `change_me` | DB password (override in `.env`) |

## Redis

| Variable | Default | Description |
|---|---|---|
| `REDIS_HOST` | `redis` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_DB` | `0` | Redis logical DB index |


## Vertex AI / Gemini

| Variable | Default | Description |
|---|---|---|
| `VERTEX_PROJECT` | -- | GCP project ID |
| `VERTEX_LOCATION` | `global` | Vertex AI region |
| `GEMINI_MODEL` | `gemini-3-flash-preview` | Gemini model used by agents |
| `GCP_SA_KEY_PATH` | `./secrets/sa-key.json` | Path to service account JSON |
| `GCLOUD_CREDENTIALS_DIR` | -- | Optional directory for additional GCP credentials |

## Cloud Run agents

| Variable | Default | Description |
|---|---|---|
| `DEL_AGENT_URL` | -- | Cloud Run URL for Clearance Delivery agent |
| `GND_AGENT_URL` | -- | Cloud Run URL for Ground Control agent |
| `TWR_AGENT_URL` | -- | Cloud Run URL for Tower agent |

## Flight plan

| Variable | Default | Description |
|---|---|---|
| `FLIGHT_PLAN_GENERATOR_KEY` | -- | flightplandatabase.com API key |

## ASR

| Variable | Default | Description |
|---|---|---|
| `ASR_HF_MODEL` | `jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper` | HuggingFace Whisper model |
| `ASR_WHISPER_LANGUAGE` | `en` | Force-decoded language |
| `ASR_WHISPER_DEVICE` | `cpu` | `cpu` or `cuda` |
| `ASR_WHISPER_COMPUTE_TYPE` | `int8` | Whisper quantisation (`int8`, `float16`, `float32`) |
| `ASR_WHISPER_BEAM_SIZE` | `5` | Beam search width |
| `ASR_REQUEST_TIMEOUT` | `30` | Per-request timeout (s) |
| `ASR_PORT` | `8000` | Container-internal ASR port |
| `ASR_LOG_LEVEL` | `info` | Uvicorn log level |
| `ASR_WORKERS` | `1` | Uvicorn worker count |
