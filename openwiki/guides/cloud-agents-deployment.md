# Cloud Agents Deployment (DEL / GND / TWR)

The three pilot agents are **not** part of docker-compose. Each one is a small FastAPI +
[google-adk](https://google.github.io/adk-docs/) app deployed to **Google Cloud Run** and
reached by the Orchestrator through `DEL_AGENT_URL` / `GND_AGENT_URL` / `TWR_AGENT_URL`.

| Agent | Source | Endpoint | Container port |
|---|---|---|---|
| DEL — Clearance Delivery | [`agents/del/`](../../agents/del/) | `POST /agents/delivery/run` | `8080` |
| GND — Ground | [`agents/gnd/`](../../agents/gnd/) | `POST /agents/ground/run` | `8080` |
| TWR — Tower | [`agents/twr/`](../../agents/twr/) | `POST /agents/tower/run` | `8082` |

Each also exposes `GET /health` and `GET /agents/<role>/info`.

## 1. GCP setup

1. Create (or pick) a GCP project and **enable the Vertex AI API**.
2. Create a service account with the **`Vertex AI User`** role.
   - For the *local* stack, download its JSON key and put it on one line in
     `GOOGLE_APPLICATION_CREDENTIALS_JSON` in `.env`.
   - For *Cloud Run*, prefer attaching the service account as the service identity —
     no key file needed.

## 2. Deploy each agent

Each agent directory has its own `Dockerfile`. Example with `gcloud` (repeat for
`del` / `gnd` / `twr`):

```bash
gcloud run deploy airport-del-agent \
  --source agents/del \
  --region europe-west1 \
  --service-account <sa-name>@<project>.iam.gserviceaccount.com \
  --set-env-vars AGENT_MODEL=gemini-3.1-flash-lite,GOOGLE_GENAI_USE_VERTEXAI=True,GOOGLE_CLOUD_PROJECT=<project>,GOOGLE_CLOUD_LOCATION=global
```

`AGENT_MODEL` is **required** — the agents read it at startup (`os.environ["AGENT_MODEL"]`).
Keep it aligned with `GEMINI_MODEL` in your `.env` (default `gemini-3.1-flash-lite`).

## 3. Wire the URLs into `.env`

```bash
DEL_AGENT_URL=https://airport-del-agent-xxxx.a.run.app
GND_AGENT_URL=https://airport-gnd-agent-xxxx.a.run.app
TWR_AGENT_URL=https://airport-twr-agent-xxxx.a.run.app
```

Then `docker compose up -d orchestrator_service` to pick them up. Note the shipped
`.env.example` has a stray `DEL_AGENT_URL=1` — replace it.

## 4. Smoke test

```bash
curl https://airport-del-agent-xxxx.a.run.app/health

curl -X POST https://airport-del-agent-xxxx.a.run.app/agents/delivery/run \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test", "message": "Iberia 5471, request IFR clearance to Barcelona."}'
```

A working agent answers with `{"session_id": ..., "reply": "<pilot readback>", ...}`.

## What the Orchestrator sends

Payload is always `{session_id, message}` plus prefetched context
(60 s timeout, see `services/orchestrator_service/agent/tools/forward.py`):

- **DEL** also receives `flight_plan` and `atis` → replies with `clearance_data`.
- **GND / TWR** also receive `clearance_data` (and a merged `taxi_route` when available).

## Costs & quotas

The agents are stateless and scale to zero on Cloud Run — you pay per request plus the
Gemini/Vertex AI usage. Watch the Vertex AI quota of your project if you run long sessions
with many aircraft. Unset or wrong `*_AGENT_URL` values are a common failure mode — see
[Troubleshooting](troubleshooting.md).

## Related

[Installation](installation.md) · [Configuration](configuration.md) · [Agents (module reference)](../agents.md)
