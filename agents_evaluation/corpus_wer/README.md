# Pilot Readback Corpus

Reference corpus for Word Error Rate (WER) evaluation of Automatic Speech Recognition (ASR) systems in Air Traffic Control (ATC) communications.

## Overview

This dataset contains realistic ATC pilot-controller dialogues covering three operational phases of a departure sequence. Each file includes controller transmissions (`>`) and pilot readbacks (`<`), written in standard ICAO radiotelephony phraseology.

## Structure

```
atc-readback-corpus/
+-- del/corpus_wer_del.txt   # Delivery (clearance delivery)
+-- gnd/corpus_wer_gnd.txt   # Ground (taxi and pushback)
+-- twr/corpus_wer_twr.txt   # Tower (takeoff clearances)
```

| Phase | File | Exchanges |
|-------|------|-----------|
| DEL - Delivery | `del/corpus_wer_del.txt` | 100 |
| GND - Ground   | `gnd/corpus_wer_gnd.txt` | 100 |
| TWR - Tower    | `twr/corpus_wer_twr.txt` | 100 |

## Format

Each exchange has an identifier, an ATC transmission (`>`), and a pilot readback (`<`):

```
[del_001]
> Ryanair four seven three, cleared to Dublin via the BELEN one GOLF departure, initial climb five thousand feet, squawk two three four one, QNH one zero one three, runway three two left.
< Cleared to Dublin via BELEN one GOLF, initial climb five thousand, squawk two three four one, QNH one zero one three, runway three two left, Ryanair four seven three.
```

## Intended Use

Designed for evaluating ASR models on ATC speech, particularly fine-tuned Whisper variants. Used as part of the **AIrport** ATC training simulator for X-Plane 12.

## LLM-as-judge evaluation of the agents' replies

The same corpus also drives an **LLM-as-judge** evaluation of the three ATC
agents' *reply generation* (the pilot readback the agent produces), scored by
`gemini-2.5-pro` on Vertex. Where `benchmark_agents.py` measures latency/schema
and `validate_agents.py` checks the structured fields, `judge_responses.py`
grades the **spoken readback text** against the controller transmission and the
reference readback.

Run from the repo root (needs `.env` with the agent URLs + Vertex config, the
`google-genai` package, and Application Default Credentials — see below):

```bash
python agents_evaluation/judge_responses.py --selftest            # 2 judge calls, no agents (sanity check)
python agents_evaluation/judge_responses.py --limit 2 --deps del  # quick end-to-end smoke
python agents_evaluation/judge_responses.py                       # full 300-entry run (~25-35 min)
python agents_evaluation/judge_responses.py --rejudge agents_evaluation/output/agent_judge_full.csv  # re-score only (no agent calls)
```

For each entry the agent call is timed (reply-generation latency) and so is the
judge call. The judge returns, per entry: `values_correct`, `completeness`,
`no_hallucination` (PASS/FAIL/N-A), `phraseology_score` (1-5), `overall`
(PASS/FAIL) and a one-line Spanish `justification`.

### Outputs (all CSV, in `agents_evaluation/output/`)

| File | Contents |
|------|----------|
| `agent_judge_full.csv` | Full per-entry dump (agent reply, structured data, both latencies, all judge fields). Source for `--rejudge` and any plotting. |
| `agent_judge_review.csv` | **Manual-review artefact** (`utf-8-sig` for Excel). Rows ordered FAIL first, then errors, then PASS, with empty `human_verdict` / `human_notes` columns to fill in. |
| `agent_judge_table_summary.csv` | Per-dependency + TOTAL: `n`, `n_pass`, `pass_rate_pct`, generation latency mean/p50/p95. The headline "how well did each agent do + how fast". |
| `agent_judge_table_dimensions.csv` | Per-dependency pass rates for each judge dimension + phraseology mean and % scoring >= 4. |
| `agent_judge_table_failures.csv` | Only FAIL entries: which dimensions failed + the justification. Catalogue of concrete failures citable in the memoria. |

The three summary tables are also pretty-printed to the console at the end of a run.

### Manual review + judge reliability

1. Open `agent_judge_review.csv` in Excel (FAIL rows are at the top). For each
   row, write `PASS` or `FAIL` in `human_verdict` (optionally a note in
   `human_notes`). You need not label every row — blanks are ignored.
2. Run `python agents_evaluation/judge_agreement.py`. It compares your verdicts
   against the judge's `judge_overall`, and writes `agent_judge_agreement.csv`
   with percent agreement and **Cohen's kappa** per dependency and overall — the
   reliability figure for the automatic judge.

### Configuration / credentials

`judge_responses.py` loads `.env` (repo root) into the environment, so it needs:
`DEL_AGENT_URL` / `GND_AGENT_URL` / `TWR_AGENT_URL`, plus
`GOOGLE_GENAI_USE_VERTEXAI=True`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`.
The judge client authenticates with Application Default Credentials — set them up
once with `gcloud auth application-default login` (or point
`GOOGLE_APPLICATION_CREDENTIALS` at a credential file). Override the judge model
with `--judge-model` or the `JUDGE_MODEL` env var. Install the SDK with
`python -m pip install google-genai`.

## License

MIT
