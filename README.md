# ✈️ AIrport — ATC Training Simulator

<div align="center">

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![X-Plane](https://img.shields.io/badge/X--Plane-12-orange.svg)
![Gemini](https://img.shields.io/badge/AI-Gemini%20%2B%20Google%20ADK-green.svg)
![Whisper](https://img.shields.io/badge/ASR-Whisper%20ATC-yellow.svg)
![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)

*AI-powered Air Traffic Control training platform. Speak to AI pilots, receive realistic clearances, and watch aircraft move in X-Plane 12.*

</div>

---

## Overview

AIrport connects a controller's voice to a fleet of AI-powered aircraft. The controller talks into a microphone; the system transcribes the audio, routes the message to the correct ATC phase agent (Delivery, Ground, or Tower), generates a realistic ICAO-compliant response, and feeds movement commands back to X-Plane 12.

Each ATC phase is handled by a dedicated AI agent running on Google Cloud Run, backed by Gemini. A central Orchestrator tracks each aircraft's lifecycle through DEL → GND → TWR and routes incoming transmissions accordingly.

---

## Architecture

![Architecture](docs/architecture.svg∫)

**Services:**

| Service | Responsibility |
|---|---|
| Controller HMI | Web UI (flight strips, ground radar), API proxy |
| ASR | Whisper transcription + callsign correction |
| Orchestrator | Agent routing, aircraft state machine |
| Flight Plan | IFR flight plan generation (flightplandatabase.com) |
| Weather | METAR, TAF, ATIS generation |

---

## ATC Agents

All three agents run on **Google Cloud Run** with Gemini and are stateless between sessions. The Orchestrator provides each agent with the relevant aircraft context (flight plan, clearances, weather) on every call.

| Agent | Frequency | Responsibilities |
|---|---|---|
| **DEL** (Clearance Delivery) | DEL | Issues IFR clearances|
| **GND** (Ground Control) | GND | Assigns pushback approval and taxi routes |
| **TWR** (Tower) | TWR | Issues takeoff / landing clearances, manages runway sequencing |

Aircraft progress through the phases: `DEL → GND → TWR`. The Orchestrator stores each aircraft's phase in PostgreSQL and routes future transmissions accordingly.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Voice ASR | [Whisper fine-tuned for ATC](https://huggingface.co/jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper) via faster-whisper |
| Voice TTS | X-Plane 12 built-in TTS |
| AI Agents | Google ADK + Gemini (`gemini-3-flash-preview`) on Cloud Run |
| Web Framework | FastAPI + Uvicorn (all services) |
| Async HTTP | httpx |
| Simulator | X-Plane 12 (Python plugin API) |
| Primary DB | PostgreSQL 15 |
| Cache | Redis 7 |
| Metrics | InfluxDB 2.7 |
| Containerization | Docker Compose |
| Package Manager | uv |

---

## Getting Started

### Prerequisites

- Docker + Docker Compose
- X-Plane 12
- Google Cloud project with Vertex AI enabled
- Service account key (JSON) with Vertex AI permissions
- Deployed DEL/GND/TWR agents on Cloud Run (see `agents/`)

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```env
# Google Cloud
VERTEX_PROJECT=your-gcp-project
VERTEX_LOCATION=global
GEMINI_MODEL=gemini-3-flash-preview
GOOGLE_APPLICATION_CREDENTIALS_JSON='{...}'   # service account JSON inline

# Cloud Run agent URLs
DEL_AGENT_URL=https://del-agent-xxxx-uc.a.run.app
GND_AGENT_URL=https://gnd-agent-xxxx-uc.a.run.app
TWR_AGENT_URL=https://twr-agent-xxxx-uc.a.run.app

# Flight plan API
FLIGHT_PLAN_GENERATOR_KEY=your-key

# Postgres credentials
POSTGRES_PASSWORD=change_me
```

### 2. Start all services

```bash
docker compose up --build
```

### 3. Open the Controller HMI

Navigate to [http://localhost:8005](http://localhost:8005)

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `VERTEX_PROJECT` | — | GCP project ID |
| `VERTEX_LOCATION` | `global` | Vertex AI region |
| `GEMINI_MODEL` | `gemini-3-flash-preview` | Gemini model used by agents |
| `DEL_AGENT_URL` | — | Cloud Run URL for DEL agent |
| `GND_AGENT_URL` | — | Cloud Run URL for GND agent |
| `TWR_AGENT_URL` | — | Cloud Run URL for TWR agent |
| `ASR_HF_MODEL` | `jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper` | Whisper model |
| `ASR_WHISPER_DEVICE` | `cpu` | `cpu` or `cuda` |
| `ASR_WHISPER_COMPUTE_TYPE` | `int8` | Whisper quantisation |
| `FLIGHT_PLAN_GENERATOR_KEY` | — | flightplandatabase.com API key |

---

## Project Status

| Component | Status |
|---|---|
| ASR (Whisper) | ✅ |
| DEL / GND / TWR agents | ✅ |
| Orchestrator | ✅ |
| Controller HMI (flight strips, ground radar) | ✅ |
| Flight Plan Service | ✅ |
| Weather / ATIS Service | ✅ |
| TTS (X-Plane built-in) | ✅ |
| X-Plane Plugin | 🚧 In progress |
| Analytics / InfluxDB dashboards | 🚧 In progress |

---

## About

This project is part of an academic research initiative. For more information, visit the professor's page:

**[taxitolearn.com/airport.html](https://taxitolearn.com/airport.html)**

