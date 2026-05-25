# Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Port already in use (5432/6379/8087/8003-8008) | Conflicting local Postgres/Redis/InfluxDB instance | Stop the local service or remap the host port in `docker-compose.yml` |
| `403 / PERMISSION_DENIED` from Vertex | Service account missing the right role | Grant `Vertex AI User`, re-mount the JSON at `GCP_SA_KEY_PATH` |
| First-run Whisper download stalls | Initial model pull from HuggingFace | Pre-warm the cache or point `ASR_HF_MODEL` to a pre-cached path |
| Plugin not showing in X-Plane | XPPython3 not installed or wrong target folder | Reinstall XPPython3 and confirm files live in `<X-Plane 12>/Resources/plugins/PythonPlugins/` |
| HMI cannot reach Orchestrator | Wrong `ORCHESTRATOR_URL` (e.g. `localhost` from inside Docker) | Use the docker network name, e.g. `http://orchestrator_service:8006` |
| Flight Plan service returns 401 | Invalid `FLIGHT_PLAN_GENERATOR_KEY` | Regenerate the key at flightplandatabase.com |
