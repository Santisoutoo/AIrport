# FAQ

Quick answers. Anything install-related lives in [Installation](installation.md);
failures live in [Troubleshooting](troubleshooting.md).

## Does the ASR need a GPU?

No. The local compose stack runs faster-whisper on CPU (`ASR_WHISPER_DEVICE=cpu`,
`int8` compute). [`services/asr_service/Dockerfile.gpu`](../../services/asr_service/Dockerfile.gpu)
exists for CUDA deployments (e.g. Cloud Run with an L4 GPU): it sets
`ASR_WHISPER_DEVICE=cuda`. CPU transcription is slower but fully functional.

## Can I run AIrport without X-Plane?

Yes, partially. The whole voice → readback loop works without the simulator: the HMI chat
shows the transcription and the pilot's reply, flight strips and clearances update. What you
lose is aircraft motion on the 3D field and the spoken TTS readback — both happen inside
X-Plane via the [plugin](xplane-plugin-setup.md).

## Can I run it without the Cloud Run agents?

The stack starts fine with empty `*_AGENT_URL`s, but dispatches produce no pilot replies —
the agents are the pilots. Deploy them once ([guide](cloud-agents-deployment.md)); they are
stateless and scale to zero, so an idle deployment costs almost nothing.

## Which airports are supported?

- **LEST (Santiago)** is the default airport in the HMI and the arrival simulator.
- **LEBL (Barcelona)** ships pre-fetched in [`data/airport_data/`](../../data/airport_data/)
  (`LEBL.dat`, `LEBL_graph.json`).

Airport data (ground network, stands) is downloaded on demand from X-Plane's gateway via
`xplane-airports`, so other ICAO codes can work — but taxi routing and stand assignment are
only validated on these two. Adding an airport means verifying its ground graph; start at
[Shared → taxi_router](../shared.md).

## Where are the models and datasets?

- ASR: [`jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper`](https://huggingface.co/jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper)
  (downloaded on first run, ~1.5 GB).
- Readback corpus: [`santiisoutoo/pilot-readback-corpus`](https://huggingface.co/datasets/santiisoutoo/pilot-readback-corpus)
  on Hugging Face (audio version available on request — see the README).
- Evaluation code: [`agents_evaluation/`](../../agents_evaluation/) — see
  [Data & Testing](../data-and-testing.md).

## License and citation

Free for non-commercial use — see [`LICENSE`](../../LICENSE). If you use AIrport in research,
cite the paper; BibTeX in the [README](../../README.md#citation).

## Related

[Installation](installation.md) · [System Overview](system-overview.md) · [Quickstart](quickstart.md)
