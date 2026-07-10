# Quickstart — your first ATC session

Assumes [Installation](installation.md), the [Cloud Run agents](cloud-agents-deployment.md)
and the [X-Plane plugin](xplane-plugin-setup.md) are done. Prefer watching first?
[Full demo on YouTube](https://www.youtube.com/watch?v=VGUzkfsCwfg).

## 1. Start everything

```bash
docker compose up
```

Open the Controller HMI at <http://localhost:8005>, then start X-Plane 12 with the plugin
loaded (backend first — the plugin needs the Orchestrator on host port `8007`).

## 2. Issue your first clearance

Pick a departure flight strip in the HMI, key the mic, and speak a Delivery instruction —
the aircraft starts in the `DEL` phase. Then walk it through the lifecycle:

```
Controller: "Iberia 5471, taxi to holding point runway 25 via Charlie."
  -> ASR (Whisper ATC)     transcribes audio + corrects callsign -> IBE5471
  -> Orchestrator          routes to GND agent (current phase: GND)
  -> GND agent (Gemini)    validates route in taxi graph, drafts readback
  -> X-Plane plugin        drives aircraft along taxiway C, holds short of 25
Pilot (TTS): "Taxi to holding point runway 25 via Charlie, Iberia 5471."
```

Typical sequence: IFR clearance (**DEL**) → pushback/taxi (**GND**) → line-up and takeoff
(**TWR**). The Orchestrator advances each aircraft's phase automatically as clearances are
acknowledged.

## 3. What to watch

- **Flight strips** — phase and clearance state per aircraft.
- **Ground radar** — aircraft moving along the taxi routes you cleared.
- **Chat/transcript** — your transmission, the corrected callsign, and the pilot readback.
- **X-Plane** — the aircraft physically taxiing; the readback spoken via TTS.
- **Arrivals** — the [Arrival Simulator](../services/arrival_simulator_service.md) keeps AI
  arrivals coming down the ILS for you to sequence.

## 4. Debrief

End the session and generate the debrief (HMI → debrief): the Orchestrator summarizes your
session from the recorded transmissions and movement events.

## Something didn't happen?

No pilot reply → agent URLs ([Troubleshooting](troubleshooting.md#gcp-auth--vertex-ai)).
No aircraft motion → plugin/backend order
([Troubleshooting](troubleshooting.md#x-plane-plugin)).

## Related

[Installation](installation.md) · [X-Plane Plugin Setup](xplane-plugin-setup.md) · [System Overview](system-overview.md)
