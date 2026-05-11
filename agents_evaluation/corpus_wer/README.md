# Pilot Readback Corpus

Reference corpus for Word Error Rate (WER) evaluation of Automatic Speech Recognition (ASR) systems in Air Traffic Control (ATC) communications.

## Overview

This dataset contains realistic ATC pilot–controller dialogues covering three operational phases of a departure sequence. Each file includes controller transmissions (`>`) and pilot readbacks (`<`), written in standard ICAO radiotelephony phraseology.

## Structure

```
atc-readback-corpus/
├── del/corpus_wer_del.txt   # Delivery (clearance delivery)
├── gnd/corpus_wer_gnd.txt   # Ground (taxi and pushback)
└── twr/corpus_wer_twr.txt   # Tower (takeoff clearances)
```

| Phase | File | Exchanges |
|-------|------|-----------|
| DEL – Delivery | `del/corpus_wer_del.txt` | 42 |
| GND – Ground   | `gnd/corpus_wer_gnd.txt` | 50 |
| TWR – Tower    | `twr/corpus_wer_twr.txt` | 50 |

## Format

Each exchange has an identifier, an ATC transmission (`>`), and a pilot readback (`<`):

```
[del_001]
> Ryanair four seven three, cleared to Dublin via the BELEN one GOLF departure, initial climb five thousand feet, squawk two three four one, QNH one zero one three, runway three two left.
< Cleared to Dublin via BELEN one GOLF, initial climb five thousand, squawk two three four one, QNH one zero one three, runway three two left, Ryanair four seven three.
```

## Intended Use

Designed for evaluating ASR models on ATC speech, particularly fine-tuned Whisper variants. Used as part of the **AIrport** ATC training simulator for X-Plane 12.

## License

MIT
