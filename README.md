# 10 years of BlueSky!
This year marks BlueSky's tenth anniversary, which we are celebrating with a two-day [workshop](https://forms.office.com/e/mXamnSYba5) on November 8-9.
![workshop programme](https://github.com/TUDelft-CNS-ATM/bluesky/blob/a20cf4497d6fc57d859970891026db7ba3574807/docs/workshop_programme.png)

# BlueSky - The Open Air Traffic Simulator

[![Open in Visual Studio Code](https://img.shields.io/static/v1?logo=visualstudiocode&label=&message=Open%20in%20Visual%20Studio%20Code&labelColor=2c2c32&color=007acc&logoColor=007acc)](https://open.vscode.dev/TUDelft-CNS-ATM/bluesky)
[![GitHub release](https://img.shields.io/github/release/TUDelft-CNS-ATM/bluesky.svg)](https://GitHub.com/TUDelft-CNS-ATM/bluesky/releases/)
![GitHub all releases](https://img.shields.io/github/downloads/TUDelft-CNS-ATM/bluesky/total?style=social)

[![PyPI version shields.io](https://img.shields.io/pypi/v/bluesky-simulator.svg)](https://pypi.python.org/pypi/bluesky-simulator/)
![PyPI - Downloads](https://img.shields.io/pypi/dm/bluesky-simulator?style=plastic)
[![PyPI license](https://img.shields.io/pypi/l/bluesky-simulator?style=plastic)](https://pypi.python.org/pypi/bluesky-simulator/)
[![PyPI pyversions](https://img.shields.io/pypi/pyversions/bluesky-simulator?style=plastic)](https://pypi.python.org/pypi/bluesky-simulator/)

BlueSky is meant as a tool to perform research on Air Traffic Management and Air Traffic Flows, and is distributed under the GNU General Public License v3.

The goal of BlueSky is to provide everybody who wants to visualize, analyze or simulate air
traffic with a tool to do so without any restrictions, licenses or limitations. It can be copied,
modified, cited, etc. without any limitations.

**Citation info:** J. M. Hoekstra and J. Ellerbroek, "[BlueSky ATC Simulator Project: an Open Data and Open Source Approach](https://www.researchgate.net/publication/304490055_BlueSky_ATC_Simulator_Project_an_Open_Data_and_Open_Source_Approach)", Proceedings of the seventh International Conference for Research on Air Transport (ICRAT), 2016.

## BlueSky Releases
BlueSky is also available as a pip package, for which periodically version releases are made. You can find the latest release here:
https://github.com/TUDelft-CNS-ATM/bluesky/releases
The BlueSky pip package is installed with the following command:

    pip install bluesky-simulator[full]

Using ZSH? Add quotes around the package name: `"bluesky-simulator[full]"`. For more installation instructions go to the Wiki.

## BlueSky Wiki
Installation and user guides are accessible at:
https://github.com/TUDelft-CNS-ATM/bluesky/wiki

## Some features of BlueSky:
- Written in the freely available, ultra-simple-hence-easy-to-learn, multi-platform language
Python 3 (using numpy and either pygame or Qt+OpenGL for visualisation) with source
- Extensible by means of self-contained [plugins](https://github.com/TUDelft-CNS-ATM/bluesky/wiki/plugin)
- Contains open source data on navaids, performance data of aircraft and geography
- Global coverage navaid and airport data
- Contains simulations of aircraft performance, flight management system (LNAV, VNAV under construction),
autopilot, conflict detection and resolution and airborne separation assurance systems
- Compatible with BADA 3.x data
- Compatible wth NLR Traffic Manager TMX as used by NLR and NASA LaRC
- Traffic is controlled via user inputs in a console window or by playing scenario files (.SCN)
containing the same commands with a time stamp before the command ("HH:MM:SS.hh>")
- Mouse clicks in traffic window are use in console for lat/lon/heading and position inputs

## Contributions
BlueSky can be considered 'perpetual beta'. We would like to encourage anyone with a strong interest in
ATM and/or Python to join us. Please feel free to comment, criticise, and contribute to this project. Please send suggestions, proposed changes or contributions through GitHub pull requests, preferably after debugging it and optimising it for run-time performance.

# AI-Based Ground ATC Agent for Conflict Resolution at LEBL in BlueSky

## **Project Overview**
This project develops an **AI-powered Tower ATC Agent** for **LEBL (Barcelona Airport)** using **BlueSky**. The system focuses on taxiway conflict resolution and runway assignments. It integrates **Multi-Agent Systems, Machine Learning, NLP, and Explainable AI (XAI)** to ensure efficient and transparent decision-making.

## **1. System Components & Technologies**
| **Component**  | **Technology Used** | **Functionality** |
|---------------|------------------|----------------|
| **1. ATC Multi-Agent System** | **Multi-Agent System (MAS)** | Manages **Ground Control operations** independently. |
| **2. NLP for ATC Communications** | **Speech-to-Text & GPT-based response system** | Allows **aircraft to interact with ATC via text-based or voice commands**. |
| **3. A\* Taxi Routing** | **A\* Search Algorithm** | Optimizes **taxi paths based on congestion and ground conditions**. |
| **4. Runway Selection** | **Game Theory (Non-Cooperative Model)** | Allocates **runways dynamically** based on **traffic flow, wind, and taxi time**. |
| **6. Explainable AI (XAI) for ATC Justifications** | **SHAP (Shapley Additive Explanations)** | Explains **why the system issued reroutes, hold-short orders, or taxi delays**. |
| **7. Computer Vision for Surveillance** | **Object Detection & Tracking** | Ensures aircraft are **following taxiway and hold-short commands correctly**. |

---

## **2. System Architecture**
### **A. ATC Ground Control Agent**
The **Ground Control AI Agent** will manage:  
1. **Taxiway Conflict Resolution**  
   - Uses **A* algorithm** for optimal taxiway routing.  
   - Detects **taxi route conflicts and suggests alternate paths**.  

2. **Pushback & Gate Assignments**  
   - Ensures **pushbacks do not interfere with taxiing aircraft**.  
   - Assigns **gates dynamically** to avoid congestion.  

3. **Runway Selection & Sequencing**  
   - Uses **Game Theory** for **optimal runway allocation**.  
   - Prioritizes **shortest taxi time & minimal crossings**.  

4. **Hold-Short & Priority Clearance Management**  
   - Issues **hold-short instructions to avoid runway incursions**.  
   - Prioritizes **departure queues dynamically**.  

### **B. Conflict Resolution Using AI**
- **LSTM Model for Predictive Conflict Detection**  
  - Predicts **taxi conflicts before they occur**.  
  - Issues **real-time rerouting suggestions**.  

- **Dynamic Rerouting & Prioritization**  
  - Modifies taxi routes using **A* Search Algorithm**.  
  - Adjusts **departure sequencing to minimize taxi congestion**.  

### **C. Explainable AI (XAI) for Justifications**
Implemented **SHAP-based explanations** to **justify Ground ATC decisions**:

#### **1. Taxi Conflict Resolution Explanations**
- **"Aircraft rerouted via Taxiway B due to bottleneck at Taxiway A"**  
  - **Justification:** High aircraft density detected at Taxiway A.  
  - **XAI Factors:** Congestion level, aircraft queue length, predicted delays.  

- **"Aircraft stopped at intersection due to simultaneous crossings"**  
  - **Justification:** Prevents a taxi conflict at a critical intersection.  
  - **XAI Factors:** Aircraft speed, crossing priority, real-time positional data.  

- **"Hold-short instruction issued at RWY 24 threshold due to expected departure clearance for another aircraft"**  
  - **Justification:** Prevents runway incursion and ensures safe sequencing.  
  - **XAI Factors:** Scheduled departure, aircraft separation rules, runway occupancy.  

#### **2. Runway Assignment Justifications**
- **"Aircraft moved to alternate runway due to wind shift"**  
  - **Justification:** Aligns with optimal wind conditions for takeoff.  
  - **XAI Factors:** METAR wind data, aircraft performance, ATC runway use policies.  

- **"Aircraft delayed on runway queue due to spacing requirement"**  
  - **Justification:** Ensures compliance with wake turbulence separation.  
  - **XAI Factors:** Aircraft type (Heavy/Medium/Light), time-based separation rules.  

### **D. NLP for Ground ATC Communication**
- Converts **spoken ATC requests into structured BlueSky commands**.  
- Generates **automated text-based clearances & reroutes**.  

---

## **4. Expected Deliverables**
By the end of **two months**, the project will produce:
✅ **A fully functional AI-based Ground ATC system in BlueSky**  
✅ **Multi-Agent AI for Ground Control & Conflict Resolution**  
✅ **Explainable AI (XAI) for taxi routing decisions**  
✅ **Deep Learning model for ground conflict prediction**  
✅ **Game Theory-based Runway Allocation**  
✅ **A*-based Taxiway Routing System**  
✅ **NLP-based ATC Communication**  
✅ **Computer Vision for Taxiway Compliance**  

---

## **5. Summary**
This **structured project** ensures that the **AI-powered Ground ATC system for LEBL** will be:
- **Efficient in handling taxiway congestion & conflict resolution**.
- **Capable of predicting taxi conflicts before they occur**.
- **Providing clear explanations for ATC decisions using XAI**.
- **Interacting with pilots via NLP-based ATC communication**.

With a **structured implementation plan**, the project is **achievable within two months** and leaves **room for future enhancements**.

---
