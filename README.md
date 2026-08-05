# Pseudopilot Automation via LLM-Based Multi-Agent Systems for ATC Training in X-Plane 12

<div align="center">

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![X-Plane](https://img.shields.io/badge/X--Plane-12-orange.svg)
![Gemini](https://img.shields.io/badge/AI-Gemini%20%2B%20Google%20ADK-green.svg)
![Whisper](https://img.shields.io/badge/ASR-Whisper%20ATC-yellow.svg)
![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)
![uv](https://img.shields.io/badge/pkg-uv-black.svg)
[![Dataset](https://img.shields.io/badge/%F0%9F%A4%97%20Dataset-pilot--readback--corpus-yellow.svg)](https://huggingface.co/datasets/santiisoutoo/pilot-readback-corpus)
[![License](https://img.shields.io/badge/license-Free%20Non--Commercial-lightgrey.svg)](LICENSE)

**[Santiago Souto Ortega](https://orcid.org/0009-0004-5648-040X)** · **[Isaac González López](https://orcid.org/0000-0003-0983-1719)**

*AI-powered Air Traffic Control training platform. Speak to AI pilots, receive realistic clearances, and watch aircraft move in X-Plane 12.*

</div>

---

## 🎬 Demo

<div align="center">

[![AIrport demo](https://img.youtube.com/vi/VGUzkfsCwfg/maxresdefault.jpg)](https://www.youtube.com/watch?v=VGUzkfsCwfg)

*Click the thumbnail to watch the full system demo on YouTube.*

</div>

---

## Abstract

The training of air traffic controllers requires practice in simulators that reproduce situations as closely as possible to those encountered in a real control tower. In these exercises, the trainee issues radio instructions to the aircraft present at the airport and must receive coherent and realistic responses, just as would occur in real operations.

Currently, for this type of training to be possible, it is necessary to rely on a team of people known as pseudopilots, whose task is to simulate the crews of each aircraft. These operators respond to the controller's communications and manage the movement of aircraft within the simulated environment. However, this training model is costly, depends on the availability of qualified personnel, and limits the number of sessions that can be carried out.

This work presents AIrport, a system that replaces pseudopilots with agents capable of behaving like real pilots within a simulated airport. In the system, the aircraft are represented by agents that interpret the received instructions, respond over the radio using natural language, and manage aircraft movements following real operational procedures.

The controller interacts with the system through voice and can observe the result of their instructions in a three-dimensional representation of the airport. In this way, a single person can carry out realistic exercises with multiple aircraft simultaneously, without the need to mobilize a support team. This reduces training costs and enables practice with greater frequency, flexibility, and scalability.

**Keywords:** *air traffic control · artificial intelligence · ATC training · aviation · simulation · virtual assistants*

The pilot readback corpus used to fine-tune the readback model is publicly available on [Hugging Face](https://huggingface.co/datasets/santiisoutoo/pilot-readback-corpus):

```bibtex
@misc{SoutoReadbackCorpus2024,
  author       = {Souto Ortega, Santiago},
  title        = {Pilot Readback Corpus},
  year         = {2024},
  publisher    = {Hugging Face},
  howpublished = {\url{https://huggingface.co/datasets/santiisoutoo/pilot-readback-corpus}}
}
```

The same agent-validation dataset is also available in audio form. The audio version is not publicly hosted -- to request access, contact [Santiago Souto Ortega](mailto:soutoortegasantiago@gmail.com).

## Overview

> **Speak into the mic.** The system transcribes your voice with Whisper-ATC, routes the message to the correct ATC agent (DEL/GND/TWR), generates an ICAO-compliant readback, and moves the aircraft in X-Plane 12 -- voice to taxi clearance in under two seconds.

A central Orchestrator tracks each aircraft's lifecycle through `DEL -> GND -> TWR` and dispatches incoming transmissions to the matching phase agent.

---

## Architecture

![Architecture](docs/diagrams/images/architecture.svg)

### Application services

All FastAPI services. Ports are host-side, exposed by Docker Compose. Other directories under `services/` are placeholders and can be ignored.

| Service | Port | Responsibility |
|---|---|---|
| Controller HMI | 8005 | Web UI (flight strips, ground radar, chat) and API gateway |
| Flight Plan | 8003 | IFR flight plan generation (flightplandatabase.com) |
| Weather | 8004 | METAR, TAF, and ATIS generation |
| ASR | 8006 | Whisper transcription + callsign correction |
| Orchestrator | 8007 | Agent routing, aircraft state machine, dispatch |
| Arrival Simulator | 8008 | Spawns AI arrivals on ILS, drives vacate sequences |

### Infrastructure

| Component | Image | Port (host:container) |
|---|---|---|
| PostgreSQL | `postgres:15-alpine` | 5432:5432 |
| Redis | `redis:7-alpine` | 6379:6379 |
| InfluxDB | `influxdb:2.7-alpine` | 8087:8086 |

---

## ATC Agents

All three agents run on **Google Cloud Run** with Gemini and are stateless. The Orchestrator provides each agent with the relevant aircraft context (flight plan, clearances, weather) on every call. Source under [agents/](agents/).

| Agent | Frequency | Responsibilities |
|---|---|---|
| **DEL** (Clearance Delivery) | DEL | Issues IFR clearances |
| **GND** (Ground Control) | GND | Pushback approval, taxi routes |
| **TWR** (Tower) | TWR | Takeoff / landing clearances, runway sequencing |

---

## Example transmission

```
Controller: "Iberia 5471, taxi to holding point runway 25 via Charlie."
  -> ASR (Whisper ATC)     transcribes audio + corrects callsign -> IBE5471
  -> Orchestrator          routes to GND agent (current phase: GND)
  -> GND agent (Gemini)    validates route in taxi graph, drafts readback
  -> X-Plane plugin        drives aircraft along taxiway C, holds short of 25
Pilot (TTS): "Taxi to holding point runway 25 via Charlie, Iberia 5471."
```

---

## Technology Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.11, [uv](https://github.com/astral-sh/uv) |
| Web framework | FastAPI + Uvicorn |
| Voice ASR | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) + [Whisper fine-tuned for ATC](https://huggingface.co/jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper) |
| AI agents | google-adk + Gemini (`gemini-3.1-flash-lite`) on Cloud Run |
| Voice TTS | X-Plane 12 built-in |
| Graph routing | networkx (taxi route graphs) |
| Simulator | X-Plane 12 + [XPPython3](https://xppython3.readthedocs.io/), xplane-airports |
| Data | PostgreSQL 15, Redis 7, InfluxDB 2.7 |
| Containerization | Docker Compose |

---

## Prerequisites

**Local:** Python 3.11, [uv](https://github.com/astral-sh/uv), Docker + Compose v2, X-Plane 12 with [XPPython3](https://xppython3.readthedocs.io/).
**Cloud:** GCP project with Vertex AI enabled, service account JSON with `Vertex AI User`, three Cloud Run agents deployed (DEL / GND / TWR -- see [agents/](agents/)).
**External APIs:** flightplandatabase.com API key.

---

## Installation

```bash
git clone https://github.com/Santisoutoo/AIrport.git
cd AIrport
uv sync
cp .env.example .env   # fill credentials -- see docs/configuration.md
docker compose up --build
```

The first run downloads the Whisper ATC model (~1.5 GB) into the `asr_hf_cache` Docker volume. Open the Controller HMI at [http://localhost:8005](http://localhost:8005).

Full walkthrough — verification steps and known `.env` gaps — in the wiki: [Installation](https://github.com/Santisoutoo/AIrport/wiki/Installation). Something failing? [Troubleshooting](https://github.com/Santisoutoo/AIrport/wiki/Troubleshooting).

---

## X-Plane Plugin Setup

The in-sim plugin is **not** installed automatically: install [XPPython3](https://xppython3.readthedocs.io/), copy [plugins/GND/](plugins/GND/) into `<X-Plane 12>/Resources/plugins/PythonPlugins/`, and install the pip dependencies into the simulator's bundled Python. Full walkthrough (scripted or manual): [X-Plane Plugin Setup](https://github.com/Santisoutoo/AIrport/wiki/X-Plane-Plugin-Setup). Start the backend (Orchestrator on port `8007`) before flying.

---

## Documentation

Full guides live in the [project wiki](https://github.com/Santisoutoo/AIrport/wiki):

| Guide | Covers |
|---|---|
| [Installation](https://github.com/Santisoutoo/AIrport/wiki/Installation) | Zero → running stack, verification, known `.env` gaps |
| [Cloud Agents Deployment](https://github.com/Santisoutoo/AIrport/wiki/Cloud-Agents-Deployment) | Deploying the DEL/GND/TWR pilots to Cloud Run |
| [X-Plane Plugin Setup](https://github.com/Santisoutoo/AIrport/wiki/X-Plane-Plugin-Setup) | XPPython3 + plugin install, scripted or manual |
| [Quickstart](https://github.com/Santisoutoo/AIrport/wiki/Quickstart) | Your first ATC session end to end |
| [Configuration](https://github.com/Santisoutoo/AIrport/wiki/Configuration) | Complete environment-variable reference |
| [Troubleshooting](https://github.com/Santisoutoo/AIrport/wiki/Troubleshooting) | Symptom → cause → fix, by area |
| [System Overview](https://github.com/Santisoutoo/AIrport/wiki/System-Overview) | Every module, what it does, how they relate |

---

<div align="center">

[Wiki](https://github.com/Santisoutoo/AIrport/wiki) · [License](LICENSE) · [Contributing](CONTRIBUTING.md) · [Dataset (Hugging Face)](https://huggingface.co/datasets/santiisoutoo/pilot-readback-corpus)

*This repository accompanies the paper "Pseudopilot Automation via LLM-Based Multi-Agent Systems for ATC Training in X-Plane 12".*

**Santiago Souto Ortega** · [soutoortegasantiago@gmail.com](mailto:soutoortegasantiago@gmail.com) · [taxitolearn.com](https://taxitolearn.com)

</div>
