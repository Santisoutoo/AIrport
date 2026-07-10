# Troubleshooting

Symptom → cause → fix, organized by area. Most first-run failures come from an incomplete
`.env` — see the "known gaps" list in [Installation](installation.md).

## Docker & Compose

| Symptom | Cause | Fix |
|---|---|---|
| `port is already allocated` (5432, 6379, 8087, 8003–8008) | A local Postgres/Redis/InfluxDB or another app owns the port | Stop the local service or remap the host port in [`docker-compose.yml`](../../docker-compose.yml) |
| Redis container exits immediately | Compose mounts `./config/redis/redis.conf`, which is **not in the repo** | `mkdir -p config/redis && touch config/redis/redis.conf` (empty = default config) |
| InfluxDB restarts / never becomes healthy | `INFLUXDB_ORG` / `INFLUXDB_BUCKET` unset (missing from `.env.example`) | Add both to `.env`; InfluxDB init also reuses `POSTGRES_PASSWORD` as admin password |
| Services keep restarting after a config change | Stale containers/volumes | `docker compose down && docker compose up --build`; add `-v` only if you accept losing DB data |

## GCP auth & Vertex AI

| Symptom | Cause | Fix |
|---|---|---|
| `403 PERMISSION_DENIED` from Vertex | Service account lacks the role, or wrong project | Grant `Vertex AI User`; check `VERTEX_PROJECT` matches the project where Vertex AI is enabled |
| ASR/Orchestrator crash parsing credentials | `GOOGLE_APPLICATION_CREDENTIALS_JSON` malformed (line breaks, unescaped quotes) | Put the whole service-account JSON on **one line** in `.env` |
| Agents time out or 401 | `DEL/GND/TWR_AGENT_URL` unset, still `=1` (the `.env.example` stray value), or pointing at a dead Cloud Run revision | Set the three URLs and smoke-test `GET /health` on each ([guide](cloud-agents-deployment.md)) |

## ASR / Whisper

| Symptom | Cause | Fix |
|---|---|---|
| First `docker compose up` seems stuck on ASR | ~1.5 GB model download from Hugging Face | Watch `docker compose logs -f asr_service`; the `asr_hf_cache` volume makes later runs fast |
| Download stalls / flaky network | Hugging Face connectivity | Pre-warm the cache or point `ASR_HF_MODEL` to a locally cached model path |
| Transcription is slow | Whisper running on CPU (`ASR_WHISPER_DEVICE=cpu`) | Expected locally; for CUDA use [`Dockerfile.gpu`](../../services/asr_service/Dockerfile.gpu) — see [FAQ](faq.md) |

## Orchestrator & networking

| Symptom | Cause | Fix |
|---|---|---|
| HMI cannot reach the Orchestrator | `ORCHESTRATOR_URL` uses `localhost` **inside** a container | Use the compose service name: `http://orchestrator_service:8006` |
| Curl to `localhost:8006` fails from the host | 8006 is the Orchestrator's **container** port; its host port is **8007** | From the host use `http://localhost:8007` ([port table](configuration.md#host-vs-container-ports)) |
| `/dispatch` answers but there is never a pilot reply | Agent URLs unset/wrong (see GCP section) or Vertex quota exhausted | Fix `*_AGENT_URL`; check Cloud Run logs for the agent |

## X-Plane plugin

| Symptom | Cause | Fix |
|---|---|---|
| Plugin missing from the Plugins menu | XPPython3 not installed, or files in the wrong folder | Re-run the [setup](xplane-plugin-setup.md); files go in `<X-Plane 12>/Resources/plugins/PythonPlugins/` |
| Plugin loads but errors on imports | pip deps not installed into XPPython3's bundled Python | Run [`docs/install/install_dependencies.bat`](../../docs/install/install_dependencies.bat) (or the `.sh`) |
| Aircraft never move / no TTS | Backend not running before the flight, or Orchestrator unreachable on host `8007` | `docker compose up` first, then start the flight; **Plugins → XPPython3 → Reload Scripts** after changes |

## Flight plans

| Symptom | Cause | Fix |
|---|---|---|
| Flight Plan service returns `401` | Invalid `FLIGHT_PLAN_GENERATOR_KEY` | Regenerate the key at flightplandatabase.com; the local fallback generator works without a key |

## Python / uv

| Symptom | Cause | Fix |
|---|---|---|
| `uv sync` fails resolving the environment | Wrong Python version active | The project targets **Python 3.11**; `uv python install 3.11` and retry |

## Related

[Installation](installation.md) · [Configuration](configuration.md) · [FAQ](faq.md)

> This page supersedes [`docs/troubleshooting.md`](../../docs/troubleshooting.md), which now
> points here.
