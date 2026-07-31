# Plan: Deploy the missing ASR Cloud Run services (parallel, incl. GPU tier)

## Context

The Whisper ASR benchmark campaign (see [`docs/plan_benchmark_whisper_asr.md`](../../Documents/personal_projects/AIrport/docs/plan_benchmark_whisper_asr.md))
needs one dedicated Cloud Run service per **model × tier** cell so latency/cost
measurements don't contaminate each other. Everything up to the build half is
already in place: the service code is modified, `Dockerfile` + `Dockerfile.gpu`
exist, and **`services/asr_service/cloudbuild.yaml` already builds+pushes a
model-baked image** (parametrized by `_ASR_HF_MODEL` / `_DOCKERFILE` / `_IMAGE_TAG`).
The one missing piece is the deploy orchestrator it names but that doesn't exist:
**`scripts/deploy_asr_matrix.sh`**. gcloud is configured (project `airport-490118`,
region `europe-west1`, Artifact Registry repo `airport`).

**Scope:** the full matrix — **10 CPU cells + 3 GPU (L4) cells = 13**. GPU is
included as an active tier (per request). Because L4 quota in the region is likely
low (default often 0–3 and only grantable from the GCP console), the GPU cells are
built and deployed but measured **quota-aware**: parallel if quota allows, otherwise
serialized (deploy → measure → teardown → next). The script surfaces a clear quota
error + console link if the L4 allocation is 0.

**Outcome:** one command builds the images and stands up the CPU services in
parallel + the GPU service(s) within quota, all smoke-tested, plus a manifest CSV
that the future `benchmark_asr.py` consumes.

## The matrix (13 cells)

Models baked at build time (all `jlvdoorn`, transformers backend):

| Short | HF model | Tiers |
|-------|----------|-------|
| `tiny`   | `jlvdoorn/whisper-tiny-atco2-asr`     | c1, c2, c3, c4, **g1** |
| `medium` | `jlvdoorn/whisper-medium-atco2-asr`   | c2, c3, c4, **g1** |
| `large`  | `jlvdoorn/whisper-large-v3-atco2-asr` | c2, c3, c4, **g1** |

`c1` (1 vCPU / 4 GiB) is tiny-only per the campaign plan. Tier → resources / cost:

| Tier | image | `--cpu` | `--memory` | GPU | cost/h |
|------|-------|---------|------------|-----|--------|
| c1 | `asr-<m>:bench` (CPU) | 1 | 4Gi | — | 0.10 |
| c2 | `asr-<m>:bench` (CPU) | 2 | 8Gi | — | 0.21 |
| c3 | `asr-<m>:bench` (CPU) | 4 | 16Gi | — | 0.42 |
| c4 | `asr-<m>:bench` (CPU) | 8 | 32Gi | — | 0.83 |
| **g1** | `asr-<m>:bench-gpu` (cu121) | 4 | 16Gi | L4 ×1 | 1.30 |

Service naming: `asr-<model>-<tier>` (e.g. `asr-tiny-c2`, `asr-large-g1`).
CPU ratios satisfy Cloud Run's memory→cpu floors; L4 requires exactly ≥4 CPU / 16 GiB.

## Design — `scripts/deploy_asr_matrix.sh` (bash, runs under Git Bash)

Follows the existing convention (the `.sh` name is already referenced by
`cloudbuild.yaml`). Subcommands:

- **`build [models…]`** — per model, launch Cloud Builds in **parallel** with
  `gcloud builds submit --config=services/asr_service/cloudbuild.yaml --async`,
  capture build IDs, poll `gcloud builds describe <id> --format='value(status)'`
  until all `SUCCESS`. Builds **both** variants per model:
  - CPU image: `_DOCKERFILE=Dockerfile, _IMAGE_TAG=asr-<model>:bench`
  - GPU image: `_DOCKERFILE=Dockerfile.gpu, _IMAGE_TAG=asr-<model>:bench-gpu`

  Up to 6 parallel builds — within the default Cloud Build concurrency quota.
  Images land in `europe-west1-docker.pkg.dev/airport-490118/airport/…`.
- **`deploy [cells…]`** — default = all 13 cells. **CPU cells** each run as a
  background job (`&`) with a single `wait` barrier. **GPU cells** deploy with a
  concurrency cap `--gpu-parallel N` (default **1** = serial, safe for quota=1;
  raise if quota permits). Shared flags: `--region=europe-west1 --port=8000
  --concurrency=1 --min-instances=1 --max-instances=1 --timeout=600
  --no-cpu-throttling --cpu-boost --allow-unauthenticated
  --update-labels=campaign=asr-bench`.
  - CPU: `--cpu`/`--memory` from table, `--set-env-vars=ASR_WHISPER_DEVICE=cpu`,
    image `asr-<model>:bench`.
  - GPU: `--gpu=1 --gpu-type=nvidia-l4 --no-gpu-zonal-redundancy --cpu=4
    --memory=16Gi --set-env-vars=ASR_WHISPER_DEVICE=cuda`, image `asr-<model>:bench-gpu`.

  (`ASR_HF_MODEL` is baked at build and **not** overridden at runtime.)
  **`ORCHESTRATOR_URL` is deliberately left unset** — this is a pure-ASR benchmark
  (WER + latency + cost + entity accuracy), so `/transcribe` must return only the
  transcription + `duration_s` and never dispatch to an agent / generate a readback.
- **`smoke [services…]`** — `GET /api/v1/asr/health` → `{"status":"ok"}`; if a sample
  wav is available, one `POST /api/v1/asr/transcribe` asserting `raw_transcription` /
  `transcription` / `duration_s`. For GPU, the log line should confirm the pipeline
  landed on CUDA (device 0), not CPU.
- **`manifest`** — regenerate `output/asr_bench/deploy_manifest.csv` from live
  services filtered by label (`model,tier,service_name,url,cpu,memory,gpu,cost_per_h`).
  Handoff to `benchmark_asr.py` (`--asr-url` / `--tier` / `--cost-per-h`).
- **`teardown [services…]`** — with no arg, delete **only** services labeled
  `campaign=asr-bench`; with args, delete named services (used to free the single L4
  between serial GPU measurements). The label guard structurally protects
  `asr-service`, `asr-service-large`, and the `*-agent` production services.
- **`pilot`** — build `tiny` (both variants) + deploy `asr-tiny-c2` + smoke; cheap
  end-to-end validation before fanning out. Add `--gpu` to also validate `asr-tiny-g1`
  (this is the cheapest way to confirm L4 quota actually exists before building the
  medium/large GPU images).
- **`all`** — `build → deploy → smoke → manifest` (CPU parallel + GPU quota-aware).

### Quota handling for G1
Cloud Run L4 quota isn't cleanly queryable from the CLI, so the script is
**optimistic-with-fallback**: it attempts the GPU deploy; on a quota/`RESOURCE_EXHAUSTED`
error it prints the exact metric + the console quota page
(`console.cloud.google.com/iam-admin/quotas`) and continues without failing the CPU
matrix. With `--gpu-parallel 1` (default), only one L4 is ever held at a time, so a
quota of 1 is enough to measure all three GPU cells sequentially.

### Why this is safe to parallelize
Each cell is an independent Cloud Run service with its own dedicated instance
(`concurrency=1`, `min/max-instances=1`), so parallel deploys don't cross-contaminate,
and `gcloud run deploy` is idempotent. Parallelizing doesn't increase billed
instance-hours — only wall-clock.

## Optional (recommended) 2-line code tweak for the GPU tier

`transcribe_service.load_model()` builds the transformers pipeline without a dtype,
so on GPU it would run **fp32**. To get the plan's intended fp16 (≈½ latency & VRAM
on L4), pass `torch_dtype=torch.float16` when `device == "cuda"` in the
`pipeline(...)` call. Small, isolated, and only affects the GPU path; without it the
GPU tier still works (fp32) but the latency numbers won't reflect fp16.

## Reused / referenced assets

- `services/asr_service/cloudbuild.yaml` — build half, already parametrized (CPU +
  GPU via `_DOCKERFILE`).
- `services/asr_service/Dockerfile` (CPU) / `Dockerfile.gpu` (cu121, `ASR_WHISPER_DEVICE=cuda`)
  + `download_model.py` — bake the HF model per `--build-arg ASR_HF_MODEL`.
- Endpoints from `services/asr_service/api/routes.py`.

## Verification (end-to-end, run the real thing)

1. **`pilot --gpu`** first: `asr-tiny-c2` (CPU) and `asr-tiny-g1` (GPU) both pass
   `/health`; a transcribe returns the three fields; the GPU service log confirms
   CUDA. This proves build→push→deploy→serve on both variants **and** confirms L4
   quota exists before building medium/large GPU images.
2. **Fan out** (`deploy` + `smoke`): all 10 CPU cells healthy in parallel; GPU cells
   healthy within quota (serial by default). Confirm
   `gcloud run services list --filter="metadata.labels.campaign=asr-bench"` lists
   exactly the campaign services and nothing else.
3. **Memory floor check:** watch `asr-large-c2` startup — large-v3 (~6 GB fp32,
   eager load) may OOM on 8 GiB; if smoke fails, drop `large-c2` as the memory floor.
4. **Teardown check:** `teardown` deletes exactly the `campaign=asr-bench` services,
   leaving `asr-service` / `asr-service-large` / `*-agent` intact.

## Risks / notes

- **GPU quota:** L4 in `europe-west1` may be 0 → the first GPU deploy fails with a
  clear message; a console quota-increase request (only Santiago can file it) may be
  needed. CPU matrix proceeds regardless.
- **GPU cost:** each `asr-<m>-g1` bills ~$1.30/h while warm (`min-instances=1`).
  Serial GPU (default) holds one L4 at a time; tear each down right after measuring.
- **Warm cost:** the 10 CPU services bill ~$3/h aggregate until teardown → benchmark
  promptly, then `teardown`. Campaign stays within the ~$5–15 envelope.
- **fp16:** without the optional code tweak the GPU tier runs fp32 (works, slower).
- **Windows:** `&`/`wait` + `gcloud … --async` polling all work under Git Bash.
- **Out of scope:** `benchmark_asr.py`, aggregation/plots, LaTeX tables — separate
  follow-ups; this plan stops at "services up, smoke-tested, manifest emitted."

## Files

- **Create:** `scripts/deploy_asr_matrix.sh` (the deliverable).
- **Create at runtime:** `output/asr_bench/deploy_manifest.csv`.
- **Optional edit:** `services/asr_service/api/transcribe_service.py` (fp16 dtype on CUDA).
- **Reuse unchanged:** `services/asr_service/cloudbuild.yaml`, `Dockerfile`,
  `Dockerfile.gpu`, `download_model.py`.
