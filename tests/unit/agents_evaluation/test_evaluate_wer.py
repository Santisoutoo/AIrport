"""Characterization tests for ``agents_evaluation/evaluate_wer.py``.

The script talks to the ASR service, the orchestrator and the filesystem, so
every I/O boundary is monkeypatched: ``transcribe``, ``dispatch`` and the
``wer`` metric are replaced, and the working directory is a tmp corpus tree
(the script resolves ``corpus_wer/`` relative to the CWD).

These tests pin the current behaviour before the refactor of ``main()``
(issue #58), including two quirks that are preserved on purpose — see the
``QUIRK`` comments.
"""

from __future__ import annotations

import csv
import importlib
import importlib.util
import sys
from pathlib import Path

import httpx
import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[3] / "agents_evaluation" / "evaluate_wer.py"
)
_MOD_NAME = "evaluate_wer_under_test"


def _load_module():
    if _MOD_NAME in sys.modules:
        return sys.modules[_MOD_NAME]
    spec = importlib.util.spec_from_file_location(_MOD_NAME, _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MOD_NAME] = module
    spec.loader.exec_module(module)
    return module


ev = _load_module()


_CORPUS_TXT = """\
# comment line ignored
[a]
> ryanair four seven three cleared to madrid
< cleared to madrid ryanair four seven three
[b]
> vueling three two alpha squawk one two three four
< squawk one two three four vueling three two alpha
"""


def _fake_wer(ref: str, hyp: str) -> float:
    """Deterministic stand-in for jiwer.wer (0.0 when identical, 0.5 otherwise)."""
    return 0.0 if ref == hyp else 0.5


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """Build a corpus tree in tmp_path and chdir into it.

    Returns the ``del`` folder so tests can add/remove .wav files.
    """
    for dep in ("del", "gnd", "twr"):
        dep_dir = tmp_path / "corpus_wer" / dep
        dep_dir.mkdir(parents=True)
        (dep_dir / f"corpus_wer_{dep}.txt").write_text(_CORPUS_TXT, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ev, "wer", _fake_wer)
    monkeypatch.setattr(ev, "ORCHESTRATOR_URL", "")
    return tmp_path / "corpus_wer" / "del"


# ---------------------------------------------------------------------------
# load_corpus
# ---------------------------------------------------------------------------


def test_load_corpus_parses_entries(tmp_path):
    path = tmp_path / "c.txt"
    path.write_text(_CORPUS_TXT, encoding="utf-8")
    corpus = ev.load_corpus(path)
    assert set(corpus) == {"a", "b"}
    assert corpus["a"]["ref"] == "ryanair four seven three cleared to madrid"
    assert corpus["a"]["readback"] == "cleared to madrid ryanair four seven three"


def test_load_corpus_entry_without_readback_is_dropped(tmp_path):
    path = tmp_path / "c.txt"
    path.write_text("[a]\n> only a reference\n", encoding="utf-8")
    assert ev.load_corpus(path) == {}


# ---------------------------------------------------------------------------
# main() — phase 1 (WER)
# ---------------------------------------------------------------------------


def test_main_exits_when_no_audio_is_processed(corpus, capsys):
    with pytest.raises(SystemExit) as exc:
        ev.main()
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Sin audios" in out
    assert "No se procesó ningún audio." in out


def test_main_reports_wer_per_audio_and_summary(corpus, monkeypatch, capsys):
    (corpus / "a.wav").write_bytes(b"")
    (corpus / "b.wav").write_bytes(b"")
    transcriptions = {
        "a": "ryanair four seven three cleared to madrid",   # exact -> WER 0.0
        "b": "something else",                               # differs -> WER 0.5
    }
    monkeypatch.setattr(ev, "transcribe", lambda p: transcriptions[p.stem])

    ev.main()

    out = capsys.readouterr().out
    assert "DEL — 2 audios" in out
    assert "[OK] a  WER=0.0%" in out
    assert "[REVISAR] b  WER=50.0%" in out
    # The reference/hypothesis pair is echoed only for non-zero WER.
    assert "REF: vueling three two alpha squawk one two three four" in out
    assert "HYP: something else" in out
    assert "Global : 25.0%  (2 audios)" in out
    assert "DEL    : 25.0%  (2 audios)" in out
    # Phase 2 is skipped when ORCHESTRATOR_URL is empty.
    assert "ORCHESTRATOR_URL no definida" in out


def test_main_skips_audio_missing_from_corpus(corpus, monkeypatch, capsys):
    (corpus / "a.wav").write_bytes(b"")
    (corpus / "zzz.wav").write_bytes(b"")
    monkeypatch.setattr(ev, "transcribe", lambda p: "ryanair four seven three cleared to madrid")

    ev.main()

    out = capsys.readouterr().out
    assert "AVISO: zzz no encontrado en el corpus" in out
    assert "(1 audios)" in out


def test_main_skips_audio_when_transcription_fails(corpus, monkeypatch, capsys):
    (corpus / "a.wav").write_bytes(b"")
    (corpus / "b.wav").write_bytes(b"")

    def _transcribe(path):
        if path.stem == "b":
            raise RuntimeError("asr down")
        return "ryanair four seven three cleared to madrid"

    monkeypatch.setattr(ev, "transcribe", _transcribe)

    ev.main()

    out = capsys.readouterr().out
    assert "ERROR b: asr down" in out
    assert "Global : 0.0%  (1 audios)" in out


def test_main_does_not_export_csv_without_orchestrator(corpus, monkeypatch, tmp_path):
    # QUIRK: the CSV export lives after the phase-2 early returns, so it never
    # runs when ORCHESTRATOR_URL is unset. Preserved by the refactor.
    (corpus / "a.wav").write_bytes(b"")
    monkeypatch.setattr(ev, "transcribe", lambda p: "x")

    ev.main()

    assert not (tmp_path / "resultados_wer.csv").exists()


# ---------------------------------------------------------------------------
# main() — phase 2 (orchestrator) and CSV export
# ---------------------------------------------------------------------------


def test_main_phase2_queries_orchestrator_and_exports_csv(corpus, monkeypatch, tmp_path, capsys):
    (corpus / "a.wav").write_bytes(b"")
    monkeypatch.setattr(ev, "transcribe", lambda p: "ryanair four seven three cleared to madrid")
    monkeypatch.setattr(ev, "ORCHESTRATOR_URL", "http://orch.test")

    calls = []

    def _dispatch(message, session_id):
        calls.append((message, session_id))
        return {
            "reply": "cleared to madrid",
            "agent": "DEL",
            "aircraft_registration": "EC-TST",
        }

    monkeypatch.setattr(ev, "dispatch", _dispatch)

    ev.main()

    assert calls == [("ryanair four seven three cleared to madrid", "a")]
    out = capsys.readouterr().out
    assert "FASE 2" in out
    assert "Matrícula           : EC-TST" in out
    assert "Respuesta DEL       : cleared to madrid" in out

    csv_path = tmp_path / "resultados_wer.csv"
    assert csv_path.exists()
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["id"] == "a"
    assert rows[0]["dep"] == "del"
    assert rows[0]["agent_reply"] == "cleared to madrid"
    assert rows[0]["agent_phase"] == "DEL"
    assert rows[0]["readback_expected"] == "cleared to madrid ryanair four seven three"


def test_main_phase2_aborts_on_connect_error(corpus, monkeypatch, tmp_path, capsys):
    (corpus / "a.wav").write_bytes(b"")
    (corpus / "b.wav").write_bytes(b"")
    monkeypatch.setattr(ev, "transcribe", lambda p: "x")
    monkeypatch.setattr(ev, "ORCHESTRATOR_URL", "http://orch.test")

    seen = []

    def _dispatch(message, session_id):
        seen.append(session_id)
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(ev, "dispatch", _dispatch)

    ev.main()

    # The loop breaks on the first connection error but still exports the CSV.
    assert seen == ["a"]
    out = capsys.readouterr().out
    assert "no se puede conectar al orquestador" in out
    assert (tmp_path / "resultados_wer.csv").exists()


def test_main_phase2_continues_after_per_audio_error(corpus, monkeypatch, capsys):
    (corpus / "a.wav").write_bytes(b"")
    (corpus / "b.wav").write_bytes(b"")
    monkeypatch.setattr(ev, "transcribe", lambda p: "x")
    monkeypatch.setattr(ev, "ORCHESTRATOR_URL", "http://orch.test")

    seen = []

    def _dispatch(message, session_id):
        seen.append(session_id)
        if session_id == "a":
            raise RuntimeError("weird")
        return {"reply": "ok", "agent": "DEL"}

    monkeypatch.setattr(ev, "dispatch", _dispatch)

    ev.main()

    assert seen == ["a", "b"]
    assert "ERROR a: weird" in capsys.readouterr().out
