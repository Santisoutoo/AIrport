import sys
from pathlib import Path

# debrief_builder lives inside the orchestrator service source; add it to sys.path
_ORCH = Path(__file__).resolve().parents[2] / "services" / "orchestrator_service"
if str(_ORCH) not in sys.path:
    sys.path.insert(0, str(_ORCH))

from debrief_builder import (
    _coerce_ts,
    _fmt_ts,
    build_timeline,
    summarise_stats,
    truncate_timeline,
)


# Fixed epoch timestamps so formatting is deterministic (UTC)
T0 = 1_776_800_000.0  # 2026-04-21 19:33:20 UTC


def test_timeline_ordering_mixes_sources():
    text = build_timeline(
        transcripts=[{"ts": T0, "text": "Iberia 3421 ready"}],
        agent_replies=[{"ts": T0 + 5, "dep": "DEL", "registration": "EC-IYV",
                        "callsign": "IBE3421", "reply": "IBE3421, cleared."}],
        events=[{"ts": T0 + 10, "registration": "EC-IYV", "event": "pushback_started"}],
        clearances=[{"updated_at": T0 + 3, "aircraft_registration": "EC-IYV",
                     "dependency": "DEL", "squawk": 2000, "runway_in_use": "06R"}],
    )
    lines = text.splitlines()
    assert len(lines) == 4
    # Chronologically: CTRL (T0), CLEARANCE (T0+3), PILOT (T0+5), EVENT (T0+10)
    assert "CTRL" in lines[0]
    assert "CLEARANCE" in lines[1]
    assert "PILOT" in lines[2]
    assert "EVENT" in lines[3]


def test_timeline_includes_quoted_text():
    text = build_timeline(
        transcripts=[{"ts": T0, "text": "taxi via tango"}],
        agent_replies=[],
        events=[],
        clearances=[],
    )
    assert '"taxi via tango"' in text


def test_timeline_event_extra_rendered():
    text = build_timeline(
        transcripts=[],
        agent_replies=[],
        events=[{"ts": T0, "registration": "EC-VBT", "event": "pushback_started",
                 "extra": {"plan_id": "abc123"}}],
        clearances=[],
    )
    assert "EVENT (EC-VBT): pushback_started" in text
    assert "plan_id=abc123" in text


def test_empty_inputs_return_empty_string():
    assert build_timeline([], [], [], []) == ""
    assert build_timeline(None, None, None, None) == ""


def test_truncate_keeps_tail_and_prepends_marker():
    long_block = "\n".join(f"[00:00:{i:02d}] CTRL: \"line {i}\"" for i in range(200))
    out = truncate_timeline(long_block, max_chars=400)
    assert out.startswith("[... ")
    # Last line preserved
    assert "line 199" in out
    assert "earlier entries omitted" in out


def test_summarise_stats_counts_and_duration():
    stats = summarise_stats(
        transcripts=[{"ts": T0}, {"ts": T0 + 60}],
        agent_replies=[
            {"ts": T0, "dep": "DEL", "registration": "EC-A"},
            {"ts": T0 + 10, "dep": "GND", "registration": "EC-A"},
            {"ts": T0 + 20, "dep": "GND", "registration": "EC-B"},
        ],
        events=[{"ts": T0 + 5}],
        clearances=[{"aircraft_registration": "EC-A"}, {"aircraft_registration": "EC-B"}],
    )
    assert stats["transcript_count"] == 2
    assert stats["agent_reply_count"] == 3
    assert stats["event_count"] == 1
    assert stats["clearance_count"] == 2
    assert stats["aircraft_count"] == 2
    assert stats["dep_reply_counts"] == {"DEL": 1, "GND": 2, "TWR": 0}
    assert stats["duration_seconds"] == 60.0


def test_missing_text_fields_skipped():
    text = build_timeline(
        transcripts=[{"ts": T0, "text": ""}],
        agent_replies=[{"ts": T0, "reply": None}],
        events=[],
        clearances=[],
    )
    assert text == ""


# ---- Timestamp handling (issue #49) -----------------------------------------
#
# `_fmt_ts` and `_coerce_ts` accept epoch floats, ISO strings and None, because
# transcripts arrive from Redis while clearances come from Postgres. The cases
# below pin every branch before the #58 refactor touches them.


def test_iso_timestamps_are_accepted_alongside_epochs():
    text = build_timeline(
        transcripts=[{"ts": "2026-04-22T13:33:20Z", "text": "first"}],
        agent_replies=[],
        events=[],
        clearances=[{"updated_at": "2026-04-22T13:33:25+00:00",
                     "aircraft_registration": "EC-IYV", "dependency": "DEL"}],
    )
    lines = text.splitlines()

    assert lines[0].startswith("[13:33:20] CTRL")
    assert lines[1].startswith("[13:33:25] CLEARANCE")


def test_iso_and_epoch_entries_sort_into_one_sequence():
    text = build_timeline(
        transcripts=[{"ts": "2026-04-22T13:33:30Z", "text": "later"}],
        agent_replies=[{"ts": T0, "reply": "earlier"}],
        events=[],
        clearances=[],
    )

    assert '"earlier"' in text.splitlines()[0]
    assert '"later"' in text.splitlines()[1]


def test_missing_timestamps_fall_back_to_the_epoch_and_sort_first():
    text = build_timeline(
        transcripts=[{"ts": T0, "text": "timed"}, {"text": "undated"}],
        agent_replies=[],
        events=[],
        clearances=[],
    )
    lines = text.splitlines()

    # `_coerce_ts(None)` is 0.0, so an undated entry is stamped 00:00:00 and
    # leads the timeline rather than being marked unknown.
    assert lines[0].startswith("[00:00:00]")
    assert '"undated"' in lines[0]
    assert lines[1].startswith("[19:33:20]")


def test_unparseable_timestamps_degrade_instead_of_raising():
    text = build_timeline(
        transcripts=[{"ts": "not a timestamp", "text": "garbled"}],
        agent_replies=[],
        events=[],
        clearances=[],
    )

    assert text.startswith("[00:00:00] CTRL")


def test_coerce_ts_branches():
    assert _coerce_ts(None) == 0.0
    assert _coerce_ts(12) == 12.0
    assert _coerce_ts(T0) == T0
    assert _coerce_ts("2026-04-21T19:33:20+00:00") == T0
    assert _coerce_ts("not a timestamp") == 0.0
    assert _coerce_ts(object()) == 0.0


def test_fmt_ts_string_and_placeholder_branches_are_unreachable_from_build_timeline():
    # `build_timeline` always pipes timestamps through `_coerce_ts` first, so
    # `_fmt_ts` only ever sees floats there. Its string and failure branches
    # survive for direct callers; pinning them keeps the refactor honest about
    # what it is allowed to delete.
    assert _fmt_ts(None) == "--:--:--"
    assert _fmt_ts("2026-04-22T13:33:20Z") == "13:33:20"
    assert _fmt_ts("not a timestamp") == "--:--:--"
    assert _fmt_ts(T0) == "19:33:20"


def test_event_extra_drops_empty_and_structured_values():
    text = build_timeline(
        transcripts=[],
        agent_replies=[],
        events=[{"ts": T0, "registration": "EC-VBT", "event": "taxi_cleared",
                 "extra": {"plan_id": "abc123", "note": "", "reason": None,
                           "route": ["A", "B"], "holds": {"n": 1}, "ok": True}}],
        clearances=[],
    )

    assert "plan_id=abc123" in text
    assert "ok=True" in text
    # Empty, null and nested values are all skipped rather than serialised.
    for skipped in ("note=", "reason=", "route=", "holds="):
        assert skipped not in text


def test_clearance_summary_skips_unset_fields():
    text = build_timeline(
        transcripts=[],
        agent_replies=[],
        events=[],
        clearances=[{"cleared_at": T0, "aircraft_registration": "EC-IYV",
                     "dependency": "DEL", "squawk": 2000, "initial_altitude": 0,
                     "runway_in_use": "", "destination_icao": None}],
    )

    assert "squawk=2000" in text
    # 0, "" and None are all treated as "not set".
    for skipped in ("initial_altitude=", "runway_in_use=", "destination_icao="):
        assert skipped not in text


def test_truncate_returns_text_unchanged_when_it_fits():
    short = "\n".join(f"line {i}" for i in range(5))

    assert truncate_timeline(short, max_chars=24000) == short


def test_truncation_always_drops_at_least_one_line():
    # The budget accounting adds a newline per kept line, so keeping every line
    # costs len(text) + 1 — one over a budget that already triggered
    # truncation. `dropped` can therefore never reach 0, which makes the
    # marker-less return at the end of truncate_timeline dead code.
    block = "\n".join(f"line {i}" for i in range(3))

    out = truncate_timeline(block, max_chars=len(block) - 1)

    assert out.startswith("[... 1 earlier entries omitted ...]")
    assert out.endswith("line 1\nline 2")
