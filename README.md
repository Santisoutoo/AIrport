# ✈️ AIrport - Advanced ATC Training Simulator v2

<div align="center">

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![X-Plane](https://img.shields.io/badge/X--Plane-12-orange.svg)
![AI](https://img.shields.io/badge/AI-CrewAI-green.svg)
![MQTT](https://img.shields.io/badge/MQTT-Eclipse%20Mosquitto-red.svg)
![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)

*Next-generation AI-powered Air Traffic Control training platform with distributed architecture, real-time voice processing, and intelligent multi-agent pilot simulation.*

🎯 **Realistic ATC Training** | 🤖 **CrewAI Multi-Agent System** | 📊 **Advanced Analytics** | 🗣️ **Bidirectional Voice Communications**

</div>

---

## 🚀 Key Features v2

### 🧠 **Advanced AI Communication System**
- **CrewAI Multi-Agent Pilots**: Specialized agents with distinct personalities and experience levels
- **Natural Phraseology Processing**: ICAO-compliant communication with contextual variations
- **Error Simulation**: AI pilots that make realistic mistakes for enhanced training
- **Adaptive Difficulty**: Dynamic scenario adjustment based on performance

### 🎤 **Real-Time Voice Processing**
- **Bidirectional ASR/TTS**: for natural pilot-controller communications
- **Multi-Frequency Support**: DEL, GND, TWR
- **Voice Recognition**: Context-aware command interpretation

### 📡 **Distributed Architecture**
- **MQTT Communication**: Real-time messaging between all system components
- **Hybrid Database System**: PostgreSQL + Redis + InfluxDB for optimal performance
- **Docker Orchestration**: Containerized services for scalability and reliability
- **Microservices Design**: Independent, fault-tolerant service architecture

---


### 📊 **Data Flow Pipeline**
```
Controller Audio → ASR → NLP Parser → MQTT → CrewAI Agents
                                              ↓
Aircraft Response ← TTS ← Response Generator ← Agent Collaboration
                                              ↓
X-Plane Movement ← Aircraft Manager ← Command Executor
```

---

## 🛠️ Technology Stack

<div align="center">

| Layer | Technology | Purpose |
|-------|------------|---------|
| **🎤 Voice Processing** | Whisper + Coqui TTS | ASR/TTS Pipeline |
| **🧠 AI Framework** | CrewAI + Llama 2 7B | Multi-agent coordination |
| **📡 Communication** | Mosquitto | Real-time messaging |
| **💾 Databases** | PostgreSQL + Redis + InfluxDB | Hybrid data storage |
| **🐳 Orchestration** | Docker Compose | Service management |
| **✈️ Visualization** | X-Plane 12 | 3D flight simulation |
| **📊 Analytics** | Grafana + InfluxDB | Performance monitoring |

</div>

---

## 🎯 Training Capabilities

### 🏃‍♂️ **Progressive Learning System**
- **Beginner Level**: Basic clearances and simple traffic patterns
- **Intermediate Level**: Complex routing and conflict resolution
- **Advanced Level**: Emergency procedures and high-density traffic
- **Expert Level**: Multi-runway operations and weather challenges

### 📈 **AI-Powered Assessment**
```
🔍 Real-time Monitoring → 🎯 Pattern Recognition → 📊 Progress Tracking → 🏆 Certification Ready
```

- **📡 Live Performance Analysis**: Real-time monitoring of communication quality
- **🔍 Error Pattern Detection**: AI identification of recurring mistakes
- **📈 Competency Tracking**: Detailed progression across ATC skills
- **🎓 Certification Assessment**: Industry-standard readiness evaluation

### 🤖 **Intelligent Pilot Behaviors**
- **Experience Simulation**: Novice to veteran pilot personalities
- **Realistic Communications**: Natural variations in pilot responses
- **Error Injection**: Simulated pilot mistakes for training scenarios
- **Context Awareness**: Situation-appropriate pilot behaviors

---

## 🏛️ Airport Infrastructure Management

### 📻 **Frequency Services**
- **🎯 DELIVERY (DEL)**: Flight plan clearances and pushback approvals
- **🚚 GROUND (GND)**: Taxi instructions and ramp coordination
- **🏗️ TOWER (TWR)**: Takeoff/landing clearances and traffic advisories

---

## 🔧 Quick Start

### 📋 **Prerequisites**
```bash
# Required Software
- Python 3.11+
- Docker & Docker Compose
- X-Plane 12
```

### 🚀 **Installation**
```bash
# Clone repository
git clone https://github.com/your-username/airport-atc-simulator.git
cd airport-atc-simulator

# Start infrastructure services
docker-compose up -d

# TODO: COMPLETE INSTALLATION GUIDE
```
--- 

## 📊 Analytics & Monitoring

### 📈 **Real-Time Dashboards**
- **System Performance**: Service health and latency monitoring
- **Training Progress**: Competency development tracking
- **Communication Quality**: ASR/TTS accuracy metrics
- **Scenario Difficulty**: Dynamic adjustment algorithms

### 🎯 **Assessment Metrics**
- **Communication Efficiency**: Response time and clarity
- **Safety Compliance**: Adherence to ATC procedures
- **Traffic Management**: Conflict resolution effectiveness
- **Phraseology Accuracy**: ICAO standard compliance

---

<div align="center">

**🛫 Ready to master Air Traffic Control with AI-powered training? 🛬**

*Experience the future of ATC education with realistic scenarios, intelligent feedback, and industry-standard procedures.*

</div>