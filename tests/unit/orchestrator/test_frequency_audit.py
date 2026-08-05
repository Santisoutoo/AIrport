"""Unit tests for services/orchestrator_service/frequency_audit.py.

This module is pure-functions: it walks controller transcripts looking for
frequency mentions (numeric AND spelled-out in EN and ES), infers which
service the controller was talking to from a keyword window, and compares
the said frequency against the airport's expected MHz.

It is the highest-coverage-per-LOC target in the codebase -- no I/O, no
external deps, deterministic output.
"""

from __future__ import annotations

from frequency_audit import (
    _DEFAULT_FREQS_MHZ,
    audit_frequencies,
    render_audit_for_prompt,
    render_audit_markdown,
)


def _t(text: str, ts: float = 1_700_000_000.0) -> dict:
    """Build a transcript entry in the shape stored in Redis."""
    return {"ts": ts, "text": text}


# ---------------------------------------------------------------------------
# Numeric detection
# ---------------------------------------------------------------------------


def test_audit_detects_numeric_freq_in_text():
    audit = audit_frequencies([_t("Tower 118.330")])
    assert audit["mentions"] == 1
    f = audit["findings"][0]
    assert f["said_freq"] == 118.330
    assert f["service"] == "TWR"
    assert f["verdict"] == "good"


def test_audit_detects_comma_as_decimal_separator():
    """ES transcripts use comma; the regex must match both."""
    audit = audit_frequencies([_t("Torre 118,330")])
    assert audit["mentions"] == 1
    assert audit["findings"][0]["said_freq"] == 118.330


def test_audit_excludes_out_of_band_freqs():
    """The regex limits to 11x/12x MHz -- 135.5 should not match."""
    audit = audit_frequencies([_t("Random number 135.5")])
    # The pattern is `1[12]\d[.,]\d{1,3}` so a leading "13" is rejected.
    assert audit["mentions"] == 0


def test_audit_includes_12x_band():
    """12x is in band (ATIS, GND, DEL frequencies live there)."""
    audit = audit_frequencies([_t("Ground 121.655")])
    assert audit["mentions"] == 1


# ---------------------------------------------------------------------------
# Spelled digits -- EN
# ---------------------------------------------------------------------------


def test_audit_detects_spelled_digits_en():
    audit = audit_frequencies([_t("Tower, contact one one eight decimal three")])
    assert audit["mentions"] >= 1
    f = next(x for x in audit["findings"] if abs(x["said_freq"] - 118.3) < 0.005)
    assert f["service"] == "TWR"


def test_audit_niner_maps_to_nine():
    audit = audit_frequencies([_t("Ground one one niner decimal three")])
    f = next(x for x in audit["findings"] if abs(x["said_freq"] - 119.3) < 0.005)
    assert f["said_freq"] == 119.3


# ---------------------------------------------------------------------------
# Spelled digits -- ES
# ---------------------------------------------------------------------------


def test_audit_detects_spelled_digits_es():
    audit = audit_frequencies([_t("Torre uno uno ocho coma tres")])
    assert audit["mentions"] >= 1
    f = next(x for x in audit["findings"] if abs(x["said_freq"] - 118.3) < 0.005)
    assert f["service"] == "TWR"


def test_audit_punto_also_works_as_decimal():
    audit = audit_frequencies([_t("Torre uno uno ocho punto tres")])
    f = next(x for x in audit["findings"] if abs(x["said_freq"] - 118.3) < 0.005)
    assert f["said_freq"] == 118.3


# ---------------------------------------------------------------------------
# Verdict logic
# ---------------------------------------------------------------------------


def test_audit_marks_good_when_freq_matches_default_expected():
    """118.330 == default TWR -- verdict good."""
    audit = audit_frequencies([_t("Tower 118.330")])
    assert audit["findings"][0]["verdict"] == "good"
    assert audit["correct"] == 1
    assert audit["incorrect"] == 0


def test_audit_marks_bad_when_freq_mismatches_expected():
    """118.500 != default TWR 118.330 -- verdict bad."""
    audit = audit_frequencies([_t("Tower 118.500")])
    assert audit["findings"][0]["verdict"] == "bad"
    assert audit["incorrect"] == 1


def test_audit_tolerance_5khz_marks_good():
    """118.335 vs 118.330 -> within 5 kHz tolerance -> good."""
    audit = audit_frequencies([_t("Tower 118.335")])
    assert audit["findings"][0]["verdict"] == "good"


def test_audit_outside_5khz_tolerance_marks_bad():
    """118.350 vs 118.330 -> 20 kHz off -> bad."""
    audit = audit_frequencies([_t("Tower 118.350")])
    assert audit["findings"][0]["verdict"] == "bad"


def test_audit_marks_unknown_when_no_service_keyword():
    """Frequency mentioned with no service hint -> unknown verdict."""
    audit = audit_frequencies([_t("contact 118.3 please")])
    assert audit["findings"][0]["verdict"] == "unknown"
    assert audit["unknown"] == 1


# ---------------------------------------------------------------------------
# Airport-specific frequencies override defaults
# ---------------------------------------------------------------------------


def test_audit_uses_airport_freqs_over_defaults():
    """When apt.dat lists TWR=118.5 for this airport, that wins over default 118.330."""
    com = [{"service": "TWR", "frequency_mhz": 118.5, "name": "Tower"}]
    audit = audit_frequencies([_t("Tower 118.500")], com_frequencies=com)
    assert audit["findings"][0]["verdict"] == "good"
    assert audit["findings"][0]["expected_freq"] == 118.5


def test_audit_airport_freqs_with_invalid_value_falls_through_to_default():
    """A malformed entry must not break the audit -- fall back to defaults."""
    com = [{"service": "TWR", "frequency_mhz": "not-a-float"}]
    audit = audit_frequencies([_t("Tower 118.330")], com_frequencies=com)
    assert audit["findings"][0]["expected_freq"] == _DEFAULT_FREQS_MHZ["TWR"]


# ---------------------------------------------------------------------------
# Service inference
# ---------------------------------------------------------------------------


def test_audit_infers_ground_service():
    audit = audit_frequencies([_t("Ground 121.655")])
    assert audit["findings"][0]["service"] == "GND"


def test_audit_infers_delivery_service():
    audit = audit_frequencies([_t("Delivery 121.805")])
    assert audit["findings"][0]["service"] == "DEL"


def test_audit_infers_atis_service():
    audit = audit_frequencies([_t("ATIS 121.980")])
    assert audit["findings"][0]["service"] == "ATIS"


def test_audit_infers_approach_service():
    audit = audit_frequencies([_t("approach 119.300")])
    assert audit["findings"][0]["service"] == "APP"


def test_audit_first_service_keyword_in_window_wins():
    """When two service keywords are in range, the first one in _SERVICE_KEYWORDS wins (TWR before GND)."""
    audit = audit_frequencies([_t("Tower or ground 118.330")])
    assert audit["findings"][0]["service"] == "TWR"


# ---------------------------------------------------------------------------
# Aggregate counts and shape
# ---------------------------------------------------------------------------


def test_audit_aggregates_counts_across_transcripts():
    transcripts = [
        _t("Tower 118.330"),  # good
        _t("Ground 121.655"),  # good
        _t("Delivery 121.900"),  # bad (default DEL is 121.805)
        _t("just chatting"),  # no mention
    ]
    audit = audit_frequencies(transcripts)
    assert audit["mentions"] == 3
    assert audit["correct"] == 2
    assert audit["incorrect"] == 1
    assert audit["unknown"] == 0


def test_audit_empty_transcripts_yield_zeroes():
    audit = audit_frequencies([])
    assert audit == {
        "mentions": 0,
        "correct": 0,
        "incorrect": 0,
        "unknown": 0,
        "findings": [],
    }


def test_audit_none_transcripts_yield_zeroes():
    audit = audit_frequencies(None)
    assert audit["mentions"] == 0


def test_audit_skips_empty_text_entries():
    audit = audit_frequencies([_t(""), _t("   "), _t("Tower 118.330")])
    assert audit["mentions"] == 1


# ---------------------------------------------------------------------------
# render_audit_markdown
# ---------------------------------------------------------------------------


def test_render_audit_markdown_empty_when_no_findings():
    md = render_audit_markdown({"mentions": 0, "findings": []})
    assert md == ""


def test_render_audit_markdown_includes_verdict_marks():
    audit = audit_frequencies([_t("Tower 118.330"), _t("Tower 118.500"), _t("contact 118.300")])
    md = render_audit_markdown(audit)
    assert "Frequency accuracy" in md
    assert "✔" in md  # good
    assert "✘" in md  # bad
    assert "·" in md  # unknown


def test_render_audit_markdown_escapes_pipe_in_quote():
    """Quote with pipe character must be escaped to avoid breaking the markdown table."""
    audit = audit_frequencies([_t("Tower 118.330 | extra | stuff")])
    md = render_audit_markdown(audit)
    # The pipe inside the quote should be escaped (\|)
    assert "\\|" in md


def test_render_audit_markdown_truncates_long_quotes():
    long_text = "x" * 200 + " Tower 118.330"
    audit = audit_frequencies([_t(long_text)])
    md = render_audit_markdown(audit)
    assert "..." in md


# ---------------------------------------------------------------------------
# render_audit_for_prompt
# ---------------------------------------------------------------------------


def test_render_audit_for_prompt_empty_when_no_findings():
    assert render_audit_for_prompt({"mentions": 0, "findings": []}) == ""


def test_render_audit_for_prompt_compact_format():
    audit = audit_frequencies([_t("Tower 118.330")])
    out = render_audit_for_prompt(audit)
    assert "FREQUENCY AUDIT" in out
    assert "1 frequency mention" in out
    assert "GOOD" in out  # verdict upper-cased
    assert "118.330" in out
