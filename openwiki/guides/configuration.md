# Configuration

Complete environment-variable reference for the AIrport stack. Copy
[`.env.example`](../../.env.example) to `.env` and fill it in — but note `.env.example`
is currently **incomplete**; the variables marked ⚠ below must be added by hand.
Authoritative source: [`docker-compose.yml`](../../docker-compose.yml) plus each service's
settings module.

## Cloud Run agents & Vertex AI

| Variable | Default | Notes |
|---|---|---|
| `DEL_AGENT_URL` / `GND_AGENT_URL` / `TWR_AGENT_URL` | — | Cloud Run URLs of the pilot agents ([deployment guide](cloud-agents-deployment.md)). `.env.example` ships a stray `DEL_AGENT_URL=1` — replace it. |
| `VERTEX_PROJECT` | — | GCP project ID. Compose forwards it as `GOOGLE_CLOUD_PROJECT` to ASR and Orchestrator. |
| `VERTEX_LOCATION` | `global` | Forwarded as `GOOGLE_CLOUD_LOCATION`. |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | Forwarded as `ASR_LLM_MODEL` (ASR corrector) and `AGENT_MODEL` (Orchestrator agent; also required by each Cloud Run agent). |
| ⚠ `GOOGLE_APPLICATION_CREDENTIALS_JSON` | — | Service-account JSON **on a single line**; read by ASR and Orchestrator (the Orchestrator entrypoint writes it to `/tmp/sa-key.json`). Missing from `.env.example`. |
| `GOOGLE_GENAI_USE_VERTEXAI` | `True` (set by compose) | Makes google-genai/adk use Vertex AI instead of an API key. |
| `GCP_SA_KEY_PATH` / `GCLOUD_CREDENTIALS_DIR` | `./secrets/sa-key.json` / — | Alternative key-file mounting paths. |

## Databases & stores

| Variable | Default | Notes |
|---|---|---|
| `POSTGRES_HOST` / `POSTGRES_PORT` | `postgres` / `5432` | Service name inside the compose network. |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `airport` / `airport_user` / `change_me` | Override the password in `.env`. The HMI receives these as `DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASS`. |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` | `redis` / `6379` / `0` | Compose also injects `REDIS_URL=redis://redis:6379` into ASR, HMI and Arrival Simulator. |
| ⚠ `INFLUXDB_ORG` / `INFLUXDB_BUCKET` | — | **Required** by the InfluxDB container init (`DOCKER_INFLUXDB_INIT_*`); missing from `.env.example`. InfluxDB admin password reuses `POSTGRES_PASSWORD`. |

## Service URLs (inside the compose network)

Compose sets these to the **internal** container ports — don't replace them with
`localhost` or host ports:

| Variable | Compose value | Consumer |
|---|---|---|
| `ORCHESTRATOR_URL` | `http://orchestrator_service:8006` | ASR (dispatch), HMI (proxy) |
| `ASR_URL` | `http://asr_service:8000/api/v1/asr` | HMI (transcribe proxy) |
| `FLIGHT_PLAN_SERVICE_URL` | `http://flight_plan_service:8000/api/v1/flight-plan` | Orchestrator, Arrival Simulator |
| `WEATHER_SERVICE_URL` | `http://weather_service:8000/api/v1/weather` | Orchestrator |
| `HMI_SERVICE_URL` | `http://controller_hmi_service:8000` | Arrival Simulator |
| `ORCHESTRATOR_SERVICE_URL` | `http://orchestrator_service:8006` | Arrival Simulator |

## Flight plans

| Variable | Default | Notes |
|---|---|---|
| `FLIGHT_PLAN_GENERATOR_KEY` | — | [flightplandatabase.com](https://flightplandatabase.com) API key; without it the service falls back to the local generator. |

## ASR (prefix `ASR_`)

| Variable | Default | Notes |
|---|---|---|
| `ASR_HF_MODEL` | `jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper` | ~1.5 GB, cached in the `asr_hf_cache` volume. |
| `ASR_WHISPER_LANGUAGE` | `en` | |
| `ASR_WHISPER_DEVICE` | `cpu` | `cuda` for GPU deployments ([`Dockerfile.gpu`](../../services/asr_service/Dockerfile.gpu), see [FAQ](faq.md)). |
| `ASR_WHISPER_COMPUTE_TYPE` | `int8` | |
| `ASR_WHISPER_BEAM_SIZE` | `5` | |
| `ASR_REQUEST_TIMEOUT` / `ASR_PORT` / `ASR_LOG_LEVEL` / `ASR_WORKERS` | `30` / `8000` / `info` / `1` | |
| `ASR_LLM_MODEL` | from `GEMINI_MODEL` | Model for the LLM callsign corrector. |

## Arrival Simulator (prefix `ARRIVAL_`)

| Variable | Default | Notes |
|---|---|---|
| `ARRIVAL_INTERVAL_S` | `120` | Seconds between spawned arrivals (the only one in compose). |
| `ARRIVAL_MIN_CONCURRENT` | `3` | Minimum concurrent arrivals kept alive. |
| `ARRIVAL_CHECK_INTERVAL_S` | `15.0` | Scheduler tick. |
| `ARRIVAL_SLOT_SEP_NM` / `ARRIVAL_SPAWN_DISTANCE_NM` / `ARRIVAL_SPAWN_ALT_AGL_FT` | `5.0` / `10.0` / `5000` | Spawn geometry on the ILS. |
| `ARRIVAL_IAS_KTS` / `ARRIVAL_VS_FPM` | `160` / `-1333` | Approach speed profile. |
| `ARRIVAL_REQUEST_AT_NM` / `ARRIVAL_DECEL_KTS_S` / `ARRIVAL_STOP_KTS` / `ARRIVAL_VACATE_KTS` | `4.0` / `4.0` / `20.0` / `15.0` | Landing/vacate profile. |

## Host vs container ports

Every app container listens on `8000` internally **except the Orchestrator, which listens on
`8006`** (its host port is `8007`). That is why `ORCHESTRATOR_URL` is
`http://orchestrator_service:8006` for containers but `http://localhost:8007` from the host
and the X-Plane plugin.

| Service | Host | Container |
|---|---|---|
| Flight Plan | 8003 | 8000 |
| Weather | 8004 | 8000 |
| Controller HMI | 8005 | 8000 |
| ASR | 8006 | 8000 |
| Orchestrator | **8007** | **8006** |
| Arrival Simulator | 8008 | 8000 |
| PostgreSQL / Redis | 5432 / 6379 | 5432 / 6379 |
| InfluxDB | 8087 | 8086 |

## Related

[Installation](installation.md) · [Troubleshooting](troubleshooting.md) · [Cloud Agents Deployment](cloud-agents-deployment.md)

> This page supersedes [`docs/configuration.md`](../../docs/configuration.md), which now
> points here.
