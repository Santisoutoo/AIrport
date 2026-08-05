import csv
import os
import sys
import httpx
from dotenv import load_dotenv
from jiwer import wer
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")

ASR_URL = os.getenv("ASR_URL", "http://localhost:8007/api/v1/asr/transcribe")
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "")

CORPUS_TXTS = {
    "del": Path("corpus_wer/del/corpus_wer_del.txt"),
    "gnd": Path("corpus_wer/gnd/corpus_wer_gnd.txt"),
    "twr": Path("corpus_wer/twr/corpus_wer_twr.txt"),
}

CORPUS_DIR = Path("corpus_wer")

DEPARTMENTS = ["del", "gnd", "twr"]

WER_OK_THRESHOLD = 0.10

CSV_PATH = Path("resultados_wer.csv")
CSV_FIELDNAMES = ["id", "dep", "wer", "ref", "hyp", "readback_expected", "agent_reply", "agent_phase"]

_SEPARATOR = "=" * 60


def load_corpus(path: Path) -> dict[str, dict]:
    """Load the corpus. Returns a dict {id -> {ref, readback}}.

    Expected format:
        [audio_id]
        > ASR reference (ATC instruction)
        < expected pilot readback
    """
    corpus = {}
    current_id = None
    ref = readback = None

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                current_id = line[1:-1]
                ref = readback = None
            elif line.startswith("> ") and current_id:
                ref = line[2:]
            elif line.startswith("< ") and current_id:
                readback = line[2:]
                corpus[current_id] = {"ref": ref, "readback": readback}

    return corpus


def transcribe(wav_path: Path) -> str:
    """Send the audio to the ASR service and return the transcription."""
    with open(wav_path, "rb") as f:
        response = httpx.post(
            ASR_URL,
            files={"audio": (wav_path.name, f, "audio/wav")},
            timeout=30.0,
        )
    response.raise_for_status()
    return response.json().get("transcription", "")


def dispatch(message: str, session_id: str) -> dict:
    """Send the transcription to the orchestrator and return the agent reply."""
    response = httpx.post(
        ORCHESTRATOR_URL,
        json={"session_id": session_id, "message": message},
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()


# ── Phase 1: WER ──────────────────────────────────────────────────────────────


def _score_audio(dep: str, wav_file: Path, corpus: dict[str, dict]) -> dict | None:
    """Transcribe one audio file and score it against the corpus reference.

    Returns the result row, or None if the audio is not in the corpus or the
    ASR call failed (both cases are reported on stdout and skipped).
    """
    audio_id = wav_file.stem
    entry = corpus.get(audio_id)
    if not entry:
        print(f"  AVISO: {audio_id} no encontrado en el corpus")
        return None

    try:
        transcription = transcribe(wav_file)
    except Exception as e:
        print(f"  ERROR {audio_id}: {e}")
        return None

    word_error = wer(entry["ref"].lower(), transcription.lower())
    status = "OK" if word_error < WER_OK_THRESHOLD else "REVISAR"

    print(f"  [{status}] {audio_id}  WER={word_error:.1%}")
    if word_error > 0:
        print(f"    REF: {entry['ref']}")
        print(f"    HYP: {transcription}")

    return {
        "id": audio_id,
        "dep": dep,
        "wer": word_error,
        "ref": entry["ref"],
        "hyp": transcription,
        "readback_expected": entry["readback"],
        "agent_reply": "",
        "agent_phase": "",
    }


def _score_department(dep: str) -> list[dict]:
    """Score every audio of one department (del/gnd/twr)."""
    corpus = load_corpus(CORPUS_TXTS[dep])
    wav_files = sorted((CORPUS_DIR / dep).glob("*.wav"))

    if not wav_files:
        print(f"[{dep.upper()}] Sin audios en corpus_wer/{dep}/ — saltando.")
        return []

    print(f"\n{_SEPARATOR}")
    print(f"  {dep.upper()} — {len(wav_files)} audios")
    print(_SEPARATOR)

    rows = [_score_audio(dep, wav_file, corpus) for wav_file in wav_files]
    return [row for row in rows if row is not None]


def run_wer_phase() -> list[dict]:
    """Run phase 1 over every department and return the result rows."""
    results: list[dict] = []
    for dep in DEPARTMENTS:
        results.extend(_score_department(dep))
    return results


# ── WER summary ───────────────────────────────────────────────────────────────


def _mean_wer(rows: list[dict]) -> float:
    return sum(r["wer"] for r in rows) / len(rows)


def print_wer_summary(results: list[dict]) -> None:
    """Print the global and per-department WER averages."""
    print(f"\n{_SEPARATOR}")
    print("  RESUMEN WER")
    print(_SEPARATOR)
    print(f"  Global : {_mean_wer(results):.1%}  ({len(results)} audios)")

    for dep in DEPARTMENTS:
        dep_rows = [r for r in results if r["dep"] == dep]
        if dep_rows:
            print(f"  {dep.upper()}    : {_mean_wer(dep_rows):.1%}  ({len(dep_rows)} audios)")

    print("\n  Objetivo: WER < 10% con modelo 'small' o 'medium'")
    print("  Cambiar modelo: WHISPER_MODEL=small docker compose up asr_service")


# ── Phase 2: DEL agent ────────────────────────────────────────────────────────


def _print_agent_reply(row: dict, resp: dict) -> None:
    print(f"\n  [{row['id']}]")
    print(f"    HYP (transcripción) : {row['hyp']}")
    print(f"    Agente              : {resp.get('agent', '?')}")
    if resp.get("aircraft_registration"):
        print(f"    Matrícula           : {resp['aircraft_registration']}")
    print(f"    Respuesta DEL       : {resp.get('reply', '')}")


def _dispatch_row(row: dict) -> dict | None:
    """Send one transcription to the orchestrator.

    Returns the response, or None to skip the row. Raises ConnectError to the
    caller so it can abort the whole phase (the orchestrator is down).
    """
    try:
        return dispatch(row["hyp"], row["id"])
    except httpx.HTTPStatusError as e:
        print(f"  ERROR {row['id']}: orquestador devolvió {e.response.status_code}")
    except httpx.ConnectError:
        raise
    except Exception as e:
        print(f"  ERROR {row['id']}: {e}")
    return None


def run_agent_phase(results: list[dict]) -> bool:
    """Query the DEL agent for every DEL row, filling agent_reply/agent_phase.

    Returns False when the phase could not run at all (no orchestrator URL or
    no DEL rows), True otherwise.
    """
    if not ORCHESTRATOR_URL:
        print("\n[INFO] ORCHESTRATOR_URL no definida — omitiendo fase 2.")
        return False

    del_results = [r for r in results if r["dep"] == "del"]
    if not del_results:
        return False

    print(f"\n{_SEPARATOR}")
    print("  FASE 2 — RESPUESTA AGENTE DEL (orquestador)")
    print(_SEPARATOR)

    for row in del_results:
        try:
            resp = _dispatch_row(row)
        except httpx.ConnectError:
            print(f"  ERROR: no se puede conectar al orquestador ({ORCHESTRATOR_URL})")
            print("  Asegúrate de que orchestrator_service está corriendo.")
            break
        if resp is None:
            continue

        row["agent_reply"] = resp.get("reply", "")
        row["agent_phase"] = resp.get("agent", "")
        _print_agent_reply(row, resp)

    return True


# ── Reporting ─────────────────────────────────────────────────────────────────


def export_csv(results: list[dict], csv_path: Path = CSV_PATH) -> None:
    """Write every result row to `csv_path`."""
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)
    print(f"\n  CSV exportado: {csv_path.resolve()}")


def main():
    results = run_wer_phase()

    if not results:
        print("\nNo se procesó ningún audio.")
        sys.exit(1)

    print_wer_summary(results)

    # NOTE: the CSV is only written when phase 2 actually ran — kept as is to
    # preserve the original behaviour (see issue #58 follow-up).
    if not run_agent_phase(results):
        return

    export_csv(results)


if __name__ == "__main__":
    main()
