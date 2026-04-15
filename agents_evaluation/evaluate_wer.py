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


def load_corpus(path: Path) -> dict[str, dict]:
    """Carga el corpus. Devuelve dict {id -> {ref, readback}}.

    Formato esperado:
        [audio_id]
        > referencia ASR (instrucción ATC)
        < readback esperado del piloto
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
    """Envía el audio al ASR y devuelve la transcripción."""
    with open(wav_path, "rb") as f:
        response = httpx.post(
            ASR_URL,
            files={"audio": (wav_path.name, f, "audio/wav")},
            timeout=30.0,
        )
    response.raise_for_status()
    return response.json().get("transcription", "")


def dispatch(message: str, session_id: str) -> dict:
    """Envía la transcripción al orquestador y devuelve la respuesta del agente."""
    response = httpx.post(
        ORCHESTRATOR_URL,
        json={"session_id": session_id, "message": message},
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()


def main():
    results = []

    # ── Fase 1: WER ───────────────────────────────────────────────────────────
    for dep in ["del", "gnd", "twr"]:
        corpus = load_corpus(CORPUS_TXTS[dep])
        wav_files = sorted((CORPUS_DIR / dep).glob("*.wav"))

        if not wav_files:
            print(f"[{dep.upper()}] Sin audios en corpus_wer/{dep}/ — saltando.")
            continue

        print(f"\n{'='*60}")
        print(f"  {dep.upper()} — {len(wav_files)} audios")
        print(f"{'='*60}")

        for wav_file in wav_files:
            audio_id = wav_file.stem
            entry = corpus.get(audio_id)
            if not entry:
                print(f"  AVISO: {audio_id} no encontrado en el corpus")
                continue

            try:
                transcription = transcribe(wav_file)
            except Exception as e:
                print(f"  ERROR {audio_id}: {e}")
                continue

            word_error = wer(entry["ref"].lower(), transcription.lower())
            status = "OK" if word_error < 0.10 else "REVISAR"

            results.append({
                "id": audio_id,
                "dep": dep,
                "wer": word_error,
                "ref": entry["ref"],
                "hyp": transcription,
                "readback_expected": entry["readback"],
                "agent_reply": "",
                "agent_phase": "",
            })

            print(f"  [{status}] {audio_id}  WER={word_error:.1%}")
            if word_error > 0:
                print(f"    REF: {entry['ref']}")
                print(f"    HYP: {transcription}")

    if not results:
        print("\nNo se procesó ningún audio.")
        sys.exit(1)

    # ── Resumen WER ───────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  RESUMEN WER")
    print(f"{'='*60}")
    avg_wer = sum(r["wer"] for r in results) / len(results)
    print(f"  Global : {avg_wer:.1%}  ({len(results)} audios)")
    for dep in ["del", "gnd", "twr"]:
        dep_r = [r for r in results if r["dep"] == dep]
        if dep_r:
            dep_wer = sum(r["wer"] for r in dep_r) / len(dep_r)
            print(f"  {dep.upper()}    : {dep_wer:.1%}  ({len(dep_r)} audios)")

    print(f"\n  Objetivo: WER < 10% con modelo 'small' o 'medium'")
    print(f"  Cambiar modelo: WHISPER_MODEL=small docker compose up asr_service")

    # ── Fase 2: Agente DEL ────────────────────────────────────────────────────
    if not ORCHESTRATOR_URL:
        print("\n[INFO] ORCHESTRATOR_URL no definida — omitiendo fase 2.")
        return

    del_results = [r for r in results if r["dep"] == "del"]
    if not del_results:
        return

    print(f"\n{'='*60}")
    print("  FASE 2 — RESPUESTA AGENTE DEL (orquestador)")
    print(f"{'='*60}")

    for r in del_results:
        try:
            resp = dispatch(r["hyp"], r["id"])
        except httpx.ConnectError:
            print(
                f"  ERROR: no se puede conectar al orquestador ({ORCHESTRATOR_URL})")
            print("  Asegúrate de que orchestrator_service está corriendo.")
            break
        except httpx.HTTPStatusError as e:
            print(
                f"  ERROR {r['id']}: orquestador devolvió {e.response.status_code}")
            continue
        except Exception as e:
            print(f"  ERROR {r['id']}: {e}")
            continue

        r["agent_reply"] = resp.get("reply", "")
        r["agent_phase"] = resp.get("agent", "")

        print(f"\n  [{r['id']}]")
        print(f"    HYP (transcripción) : {r['hyp']}")
        print(f"    Agente              : {resp.get('agent', '?')}")
        if resp.get("aircraft_registration"):
            print(f"    Matrícula           : {resp['aircraft_registration']}")
        print(f"    Respuesta DEL       : {resp.get('reply', '')}")

    # ── Exportar CSV ──────────────────────────────────────────────────────────
    csv_path = Path("resultados_wer.csv")
    fieldnames = ["id", "dep", "wer", "ref", "hyp",
                  "readback_expected", "agent_reply", "agent_phase"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    print(f"\n  CSV exportado: {csv_path.resolve()}")


if __name__ == "__main__":
    main()
