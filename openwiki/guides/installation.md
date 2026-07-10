# Installation

From zero to a running AIrport stack. After this page: deploy the
[Cloud Run agents](cloud-agents-deployment.md), set up the
[X-Plane plugin](xplane-plugin-setup.md), then fly the [Quickstart](quickstart.md).

## Prerequisites

- **Python 3.11** and [uv](https://github.com/astral-sh/uv)
- **Docker + Compose v2**
- A **GCP project with Vertex AI enabled** and a service account with the `Vertex AI User`
  role (used by the ASR corrector, the Orchestrator and the pilot agents)
- A [flightplandatabase.com](https://flightplandatabase.com) API key
- **X-Plane 12** — only for the in-sim part; the backend runs without it
  (see [FAQ](faq.md))

## Steps

```bash
git clone https://github.com/Santisoutoo/AIrport.git
cd AIrport
uv sync
cp .env.example .env    # fill in credentials — see Configuration
docker compose up --build
```

Open the Controller HMI at <http://localhost:8005>.

> **First run:** the ASR service downloads the Whisper ATC model
> (`jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper`, ~1.5 GB) into the
> `asr_hf_cache` Docker volume. Later runs reuse the cache and start fast.

## Complete your `.env` — known gaps

[`.env.example`](../../.env.example) does not currently list everything
[`docker-compose.yml`](../../docker-compose.yml) consumes. Before the first
`docker compose up`:

1. **Add** `INFLUXDB_ORG=<org>` and `INFLUXDB_BUCKET=<bucket>` — the InfluxDB container
   needs them to initialize.
2. **Add** `GOOGLE_APPLICATION_CREDENTIALS_JSON` with your service-account JSON on a single
   line — the ASR and Orchestrator containers read it.
3. **Fix** `DEL_AGENT_URL=1` — it ships with a stray placeholder value; set the three
   `DEL/GND/TWR_AGENT_URL` to your Cloud Run URLs (or leave them empty until you deploy the
   agents; see [Cloud Agents Deployment](cloud-agents-deployment.md)).
4. **Create** `config/redis/redis.conf` — compose mounts it into the Redis container but the
   file is not in the repo; an empty file (default Redis config) is enough:
   `mkdir -p config/redis && touch config/redis/redis.conf`

Full variable reference: [Configuration](configuration.md).

## Verify the install

| Service | Host port | Check |
|---|---|---|
| Controller HMI | `8005` | <http://localhost:8005> loads · `GET /api/v1/hmi/health` |
| Flight Plan | `8003` | `GET /api/v1/flight-plan/health` |
| Weather | `8004` | `GET /api/v1/weather/health` |
| ASR | `8006` | `GET /api/v1/asr/health` (after the model download) |
| Orchestrator | `8007` | `GET /health` |
| Arrival Simulator | `8008` | `GET /api/v1/arrivals/health` |
| PostgreSQL / Redis / InfluxDB | `5432` / `6379` / `8087` | `docker compose ps` shows them healthy |

All app containers listen on port `8000` internally except the Orchestrator (`8006`) — the
table above shows host-side ports. Anything failing → [Troubleshooting](troubleshooting.md).

## Next steps

1. [Cloud Agents Deployment](cloud-agents-deployment.md) — without the three agents the
   Orchestrator cannot generate pilot readbacks.
2. [X-Plane Plugin Setup](xplane-plugin-setup.md) — to see aircraft move in the simulator.
3. [Quickstart](quickstart.md) — run your first session.

## Related

[Configuration](configuration.md) · [Troubleshooting](troubleshooting.md) · [System Overview](system-overview.md)
