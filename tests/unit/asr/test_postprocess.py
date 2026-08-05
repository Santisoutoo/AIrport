"""Characterization tests for the ASR postprocessing pipeline.

These tests pin the *current* behaviour of
``services/asr_service/core/postprocess.py`` — in particular the callsign span
finder ``_find_callsign_span`` — so it can be refactored safely (issue #58).

A couple of the expectations below encode behaviour that is arguably wrong
(see the ``QUIRK`` comments); they are recorded as-is on purpose, because the
refactor must not change what the pipeline produces.

The module is loaded by path under the synthetic package name ``asr_core``:
``services/asr_service`` cannot simply be put on ``sys.path`` because the
arrival simulator service (already on ``sys.path`` via the root conftest)
also ships a top-level ``core`` package.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

_ASR_CORE_DIR = (
    Path(__file__).resolve().parents[3] / "services" / "asr_service" / "core"
)
_PKG = "asr_core"


def _load_asr_core_package():
    if _PKG not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            _PKG,
            _ASR_CORE_DIR / "__init__.py",
            submodule_search_locations=[str(_ASR_CORE_DIR)],
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[_PKG] = module
        spec.loader.exec_module(module)
    return importlib.import_module(f"{_PKG}.postprocess")


pp = _load_asr_core_package()


def _span(text: str, at_end: bool):
    return pp._find_callsign_span(pp._alpha_tokens(text), at_end)


# ---------------------------------------------------------------------------
# _find_callsign_span
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["ab cd", "a b c", "", "one two"])
def test_span_needs_at_least_three_tokens(text):
    assert _span(text, at_end=False) is None
    assert _span(text, at_end=True) is None


def test_span_at_start_single_word_airline():
    assert _span("Vueling three two alpha cleared to Madrid", at_end=False) == (
        0, 23, "Vueling", "32A",
    )


def test_span_at_start_two_word_airline():
    assert _span("Air Nostrum one two three go", at_end=False) == (
        0, 25, "Air Nostrum", "123",
    )


def test_span_at_start_requires_two_code_words():
    assert _span("Vueling three cleared", at_end=False) is None


def test_span_at_start_stops_after_five_code_words():
    # Only the first five phonetic words are consumed as the code.
    assert _span(
        "Vueling one two three four five six seven eight", at_end=False,
    ) == (0, 31, "Vueling", "12345")


def test_span_at_start_rejects_phonetic_airline():
    assert _span("one two three four five", at_end=False) is None


def test_span_at_end_reads_code_then_airline():
    # QUIRK: the "at end" branch expects <code> <airline> (the airline is the
    # LAST token), which is the reverse of real phraseology
    # ("..., Ryanair four seven three"). See the note in the issue #58 PR.
    assert _span("cleared one two three roger", at_end=True) == (8, 27, "roger", "123")
    assert _span("cleared one two three air europa", at_end=True) == (
        8, 32, "air europa", "123",
    )


def test_span_at_end_misses_trailing_callsign():
    # QUIRK (same root cause): a trailing callsign is NOT detected.
    assert _span("Roger cleared for takeoff, Ryanair four seven three", at_end=True) is None


# ---------------------------------------------------------------------------
# Number normalisation
# ---------------------------------------------------------------------------


def test_normalize_numbers_known_contexts():
    text = (
        "squawk one two three four QNH one zero one three runway one seven left "
        "climb five thousand flight level one zero zero "
        "contact one two one decimal six five five"
    )
    assert pp.normalize_numbers(text) == (
        "squawk 1234 QNH 1013 runway 17L climb 5000 FL100 contact 121.655"
    )


def test_normalize_numbers_leaves_unknown_contexts_alone():
    assert pp.normalize_numbers("hold short of one two") == "hold short of one two"


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


def test_pipeline_compacts_callsign_to_icao_without_session():
    out = pp.postprocess_transcription("Ryanair four seven three, squawk one two three four")
    assert out["after_number_norm"] == "Ryanair four seven three, squawk 1234"
    assert out["final"] == "RYR473, squawk 1234"
    assert out["cs_icao"] == "RYR473"
    assert out["cs_fuzzy_score"] == 0.0
    assert out["cs_unknown_airline"] is False


def test_pipeline_snaps_to_session_callsign():
    out = pp.postprocess_transcription("Bowling three two alpha", ["VLG32A"])
    # "Bowling" is a known Whisper typo for "Vueling" (core.corrections).
    assert out["final"] == "VLG32A"
    assert out["cs_fuzzy_score"] == 100.0


def test_pipeline_keeps_icao_form_when_session_match_is_poor():
    out = pp.postprocess_transcription("Vueling three two alpha", ["RYR473"])
    assert out["final"] == "VLG32A"
    assert out["cs_fuzzy_score"] < pp.FUZZY_THRESHOLD


def test_pipeline_flags_unknown_airline():
    out = pp.postprocess_transcription("Fictional four seven bravo report ready")
    assert out["final"] == "Fictional 47B report ready"
    assert out["cs_unknown_airline"] is True


def test_pipeline_ignores_sid_tail_masquerading_as_callsign():
    out = pp.postprocess_transcription("Cleared via BELEN one golf departure")
    # "departure" is in _NON_AIRLINE_WORDS, so the end span is discarded.
    assert out["after_callsign_fix"] == "Cleared via BELEN one golf departure"
    assert out["final"] == "Cleared via BELEN1G departure"
    assert out["cs_icao"] is None


def test_pipeline_overlapping_start_and_end_spans():
    # QUIRK: both spans are found and applied, so the trailing "roger" is
    # swallowed by the replacement. Recorded to lock current behaviour.
    out = pp.postprocess_transcription("Air Europa one two three roger")
    assert out["final"] == "AEA123"


def test_pipeline_sid_phrase_snaps_to_session_sid():
    out = pp.postprocess_transcription(
        "cleared via BELEN one golf departure", None, ["BELEN1G"],
    )
    assert out["final"] == "cleared via BELEN1G departure"
    assert out["sid_fuzzy_candidate"] == "BELEN1G"
    assert out["sid_fuzzy_score"] == 100.0


def test_pipeline_expands_isolated_phonetic_letters_last():
    out = pp.postprocess_transcription("taxi via alpha bravo charlie delta echo foxtrot golf")
    assert out["final"] == "taxi via A B C D E F G"


def test_normalize_reference_returns_final_string():
    assert pp.normalize_reference(
        "Vueling three two alpha squawk one two three four",
    ) == "VLG32A squawk 1234"
