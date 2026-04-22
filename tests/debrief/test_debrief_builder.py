import sys
from pathlib import Path

# debrief_builder lives inside the orchestrator service source; add it to sys.path
_ORCH = Path(__file__).resolve().parents[2] / "services" / "orchestrator_service"
if str(_ORCH) not in sys.path:
    sys.path.insert(0, str(_ORCH))

from debrief_builder import build_timeline, summarise_stats, truncate_timeline


# Fixed epoch timestamps so formatting is deterministic (UTC)
T0 = 1_776_800_000.0  # 2026-04-22 13:33:20 UTC


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
