"""Characterization tests for ``debrief_builder.build_timeline``.

`build_timeline` has degree 40 and cognitive complexity 29: it folds four
heterogeneous record streams (controller transcripts, pilot agent replies, sim
events, Postgres clearance rows) into one chronological text block, and every
stream has its own skip rules, fallbacks and formatting quirks.
`tests/debrief/test_debrief_builder.py` covers the happy path; this module
pins down the *edges* — the exact rules that decide whether a record produces a
line at all, what the line looks like, and how ties are ordered.

These are characterization tests: they assert what the code does **today**,
correct or not, so a later refactor can be shown to change nothing. Where the
current behavior looks debatable it is called out in the test docstring rather
than "fixed".
"""

from __future__ import annotations

import sys
from pathlib import Path

# debrief_builder lives inside the orchestrator service source; add it to sys.path
_ORCH = Path(__file__).resolve().parents[2] / "services" / "orchestrator_service"
if str(_ORCH) not in sys.path:
    sys.path.insert(0, str(_ORCH))

import pytest

from debrief_builder import build_timeline


# 2026-04-22 13:33:20 UTC — fixed so the rendered HH:MM:SS is deterministic.
# (Note: the T0 in test_debrief_builder.py is a different, rounder epoch whose
# comment says 13:33:20 but actually resolves to 19:33:20 UTC. That file never
# asserts the rendered clock, so it does not matter there; here it does.)
T0 = 1_776_864_800.0
T0_HHMMSS = "13:33:20"


def _lines(**kwargs) -> list[str]:
    """Call build_timeline with empty defaults for the streams not given."""
    payload = {"transcripts": [], "agent_replies": [], "events": [], "clearances": []}
    payload.update(kwargs)
    text = build_timeline(**payload)
    return text.splitlines() if text else []


# ---------------------------------------------------------------------------
# Timestamp coercion and rendering
# ---------------------------------------------------------------------------


def test_epoch_float_renders_as_utc_hhmmss():
    assert _lines(transcripts=[{"ts": T0, "text": "hello"}]) == [f'[{T0_HHMMSS}] CTRL: "hello"']


def test_iso_8601_timestamp_is_coerced_then_rendered_as_utc():
    """ISO strings (with and without the Z suffix) are accepted and converted."""
    lines = _lines(
        transcripts=[
            {"ts": "2026-04-22T13:33:20Z", "text": "with Z"},
            {"ts": "2026-04-22T13:33:21+00:00", "text": "with offset"},
        ]
    )
    assert lines == [
        f'[{T0_HHMMSS}] CTRL: "with Z"',
        '[13:33:21] CTRL: "with offset"',
    ]


def test_missing_and_unparseable_timestamps_collapse_to_epoch_zero():
    """A missing or garbage ``ts`` becomes 0.0 — so the entry renders as
    00:00:00 and sorts to the very top of the timeline, ahead of real ones."""
    lines = _lines(
        transcripts=[
            {"ts": T0, "text": "real"},
            {"text": "no ts at all"},
            {"ts": "not-a-date", "text": "garbage ts"},
        ]
    )
    assert lines[0] == '[00:00:00] CTRL: "no ts at all"'
    assert lines[1] == '[00:00:00] CTRL: "garbage ts"'
    assert lines[2] == f'[{T0_HHMMSS}] CTRL: "real"'


def test_numeric_string_timestamp_is_accepted_as_epoch():
    """``_coerce_ts`` falls through to ISO parsing for strings, and
    ``fromisoformat`` rejects a bare number — so "1776800000.0" is NOT read as
    an epoch; it degrades to 0.0."""
    assert _lines(transcripts=[{"ts": str(T0), "text": "x"}]) == ['[00:00:00] CTRL: "x"']


# ---------------------------------------------------------------------------
# CTRL lines (transcripts)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "   ", "\n\t ", None])
def test_transcripts_without_usable_text_produce_no_line(text):
    assert _lines(transcripts=[{"ts": T0, "text": text}]) == []


def test_transcript_text_is_stripped_but_inner_spacing_kept():
    assert _lines(transcripts=[{"ts": T0, "text": "  taxi  via  tango  "}]) == [
        f'[{T0_HHMMSS}] CTRL: "taxi  via  tango"'
    ]


def test_transcript_quotes_are_not_escaped():
    """Embedded double quotes are passed through verbatim — the LLM prompt is
    plain text, not JSON, so no escaping happens."""
    assert _lines(transcripts=[{"ts": T0, "text": 'say "again"'}]) == [f'[{T0_HHMMSS}] CTRL: "say "again""']


# ---------------------------------------------------------------------------
# PILOT lines (agent replies)
# ---------------------------------------------------------------------------


def test_pilot_line_full_shape():
    assert _lines(
        agent_replies=[
            {
                "ts": T0,
                "dep": "GND",
                "registration": "EC-IYV",
                "callsign": "IBE3421",
                "reply": "Taxi via T, IBE3421",
            }
        ]
    ) == [f'[{T0_HHMMSS}] PILOT (GND, EC-IYV/IBE3421): "Taxi via T, IBE3421"']


def test_pilot_line_falls_back_to_registration_when_callsign_missing():
    assert _lines(agent_replies=[{"ts": T0, "dep": "DEL", "registration": "EC-IYV", "reply": "roger"}]) == [
        f'[{T0_HHMMSS}] PILOT (DEL, EC-IYV/EC-IYV): "roger"'
    ]


def test_pilot_line_uses_dashes_when_registration_and_dep_missing():
    assert _lines(agent_replies=[{"ts": T0, "reply": "roger"}]) == [f'[{T0_HHMMSS}] PILOT (-, -/-): "roger"']


@pytest.mark.parametrize("reply", ["", "   ", None])
def test_agent_replies_without_usable_reply_produce_no_line(reply):
    assert _lines(agent_replies=[{"ts": T0, "dep": "DEL", "reply": reply}]) == []


def test_error_replies_are_kept_in_the_timeline():
    """`forward_to_agent` stores "[ERROR] ..." strings as replies when a Cloud
    Run agent is down. They are NOT filtered out — the instructor sees them."""
    assert _lines(agent_replies=[{"ts": T0, "dep": "GND", "reply": "[ERROR] could not reach GND agent"}]) == [
        f'[{T0_HHMMSS}] PILOT (GND, -/-): "[ERROR] could not reach GND agent"'
    ]


# ---------------------------------------------------------------------------
# EVENT lines
# ---------------------------------------------------------------------------


def test_event_with_no_fields_at_all_still_produces_a_line():
    """Unlike transcripts/replies, events are never skipped: an empty dict
    yields a fully defaulted line."""
    assert _lines(events=[{}]) == ["[00:00:00] EVENT (-): event"]


def test_event_extra_renders_scalars_in_insertion_order():
    assert _lines(
        events=[
            {
                "ts": T0,
                "registration": "EC-VBT",
                "event": "pushback_started",
                "extra": {"plan_id": "abc123", "legs": 3, "ok": True, "dist": 1.5},
            }
        ]
    ) == [f"[{T0_HHMMSS}] EVENT (EC-VBT): pushback_started plan_id=abc123 legs=3 ok=True dist=1.5"]


def test_event_extra_drops_empty_and_non_scalar_values():
    """None, "" and any container value are omitted; note that 0 and False are
    kept, because the filter tests ``v is None or v == ""``... and ``0 == ""``
    is False in Python, so falsy numbers survive."""
    assert _lines(
        events=[
            {
                "ts": T0,
                "registration": "EC-VBT",
                "event": "taxi_done",
                "extra": {
                    "gone_none": None,
                    "gone_empty": "",
                    "gone_list": [1, 2],
                    "gone_dict": {"a": 1},
                    "kept_zero": 0,
                    "kept_false": False,
                },
            }
        ]
    ) == [f"[{T0_HHMMSS}] EVENT (EC-VBT): taxi_done kept_zero=0 kept_false=False"]


def test_event_extra_that_is_not_a_dict_is_ignored_silently():
    assert _lines(events=[{"ts": T0, "registration": "EC-VBT", "event": "x", "extra": "some string"}]) == [
        f"[{T0_HHMMSS}] EVENT (EC-VBT): x"
    ]


def test_event_extra_with_only_dropped_values_leaves_no_trailing_space():
    assert _lines(events=[{"ts": T0, "registration": "EC-VBT", "event": "x", "extra": {"a": None}}]) == [
        f"[{T0_HHMMSS}] EVENT (EC-VBT): x"
    ]


# ---------------------------------------------------------------------------
# CLEARANCE lines
# ---------------------------------------------------------------------------


def test_clearance_summary_lists_only_the_five_whitelisted_fields_in_order():
    """`clearance_text`, `altimeter` and every other column are deliberately
    NOT summarised — only these five, always in this fixed order."""
    assert _lines(
        clearances=[
            {
                "updated_at": T0,
                "aircraft_registration": "EC-IYV",
                "dependency": "DEL",
                # deliberately shuffled relative to the output order
                "destination_icao": "LEPA",
                "runway_in_use": "06R",
                "squawk": 2000,
                "instrumental_departure": "VAR1A",
                "initial_altitude": 6000,
                "altimeter": 1013.0,
                "clearance_text": "cleared to LEPA",
            }
        ]
    ) == [
        f"[{T0_HHMMSS}] CLEARANCE (EC-IYV, DEL): squawk=2000 initial_altitude=6000 "
        "instrumental_departure=VAR1A runway_in_use=06R destination_icao=LEPA"
    ]


def test_clearance_drops_none_empty_and_zero_valued_fields():
    """Zero is treated as "unset" here (unlike in event extras) — the runner
    upserts squawk=0/initial_altitude=0 placeholder rows for arrivals."""
    assert _lines(
        clearances=[
            {
                "updated_at": T0,
                "aircraft_registration": "EC-NEW",
                "dependency": "GND",
                "squawk": 0,
                "initial_altitude": 0,
                "instrumental_departure": "",
                "runway_in_use": None,
                "destination_icao": "",
            }
        ]
    ) == [f"[{T0_HHMMSS}] CLEARANCE (EC-NEW, GND):"]


def test_clearance_falls_back_to_cleared_at_when_updated_at_is_absent():
    assert _lines(clearances=[{"cleared_at": T0, "aircraft_registration": "EC-IYV", "dependency": "DEL"}]) == [
        f"[{T0_HHMMSS}] CLEARANCE (EC-IYV, DEL):"
    ]


def test_clearance_falsy_updated_at_falls_through_to_cleared_at():
    """The fallback uses ``or``, not a key check, so updated_at=0 also falls
    through to cleared_at."""
    assert _lines(
        clearances=[
            {
                "updated_at": 0,
                "cleared_at": T0,
                "aircraft_registration": "EC-IYV",
                "dependency": "DEL",
            }
        ]
    ) == [f"[{T0_HHMMSS}] CLEARANCE (EC-IYV, DEL):"]


def test_clearance_defaults_registration_and_dependency_to_dashes():
    assert _lines(clearances=[{"updated_at": T0}]) == [f"[{T0_HHMMSS}] CLEARANCE (-, -):"]


# ---------------------------------------------------------------------------
# Interleaving and ordering
# ---------------------------------------------------------------------------


def test_records_with_equal_timestamps_keep_stream_processing_order():
    """Ties are broken by the order the streams are processed — transcripts,
    then replies, then events, then clearances — because ``list.sort`` is
    stable. Any refactor that reorders the four loops changes this output."""
    lines = _lines(
        transcripts=[{"ts": T0, "text": "ctrl"}],
        agent_replies=[{"ts": T0, "dep": "DEL", "reply": "pilot"}],
        events=[{"ts": T0, "registration": "EC-IYV", "event": "ev"}],
        clearances=[{"updated_at": T0, "aircraft_registration": "EC-IYV", "dependency": "DEL"}],
    )
    assert [line.split("] ")[1].split(" ")[0].rstrip(":") for line in lines] == [
        "CTRL",
        "PILOT",
        "EVENT",
        "CLEARANCE",
    ]


def test_full_departure_session_renders_in_chronological_order():
    """End-to-end shape of a realistic DEL -> GND slice of a session."""
    text = build_timeline(
        transcripts=[
            {"ts": T0, "text": "Iberia 3421 request IFR clearance to Palma"},
            {"ts": T0 + 30, "text": "Iberia 3421 contact ground on 121.9"},
        ],
        agent_replies=[
            {
                "ts": T0 + 8,
                "dep": "DEL",
                "registration": "EC-IYV",
                "callsign": "IBE3421",
                "reply": "Cleared to Palma, VAR1A departure, squawk 2000, IBE3421",
            },
            {"ts": T0 + 33, "dep": "GND", "registration": "EC-IYV", "callsign": "IBE3421", "reply": "121.9, IBE3421"},
        ],
        events=[{"ts": T0 + 60, "registration": "EC-IYV", "event": "pushback_started"}],
        clearances=[
            {
                "updated_at": T0 + 10,
                "aircraft_registration": "EC-IYV",
                "dependency": "GND",
                "squawk": 2000,
                "runway_in_use": "06R",
            }
        ],
    )
    assert text.splitlines() == [
        f'[{T0_HHMMSS}] CTRL: "Iberia 3421 request IFR clearance to Palma"',
        '[13:33:28] PILOT (DEL, EC-IYV/IBE3421): "Cleared to Palma, VAR1A departure, squawk 2000, IBE3421"',
        "[13:33:30] CLEARANCE (EC-IYV, GND): squawk=2000 runway_in_use=06R",
        '[13:33:50] CTRL: "Iberia 3421 contact ground on 121.9"',
        '[13:33:53] PILOT (GND, EC-IYV/IBE3421): "121.9, IBE3421"',
        "[13:34:20] EVENT (EC-IYV): pushback_started",
    ]


def test_none_streams_are_treated_as_empty():
    assert build_timeline(None, None, None, None) == ""
    assert build_timeline(None, [{"ts": T0, "dep": "DEL", "reply": "r"}], None, None) == (
        f'[{T0_HHMMSS}] PILOT (DEL, -/-): "r"'
    )


def test_generators_are_accepted_as_input_streams():
    """The signature says ``Iterable``; each stream is consumed exactly once."""
    text = build_timeline(
        transcripts=(t for t in [{"ts": T0, "text": "gen"}]),
        agent_replies=iter([]),
        events=iter([]),
        clearances=iter([]),
    )
    assert text == f'[{T0_HHMMSS}] CTRL: "gen"'


def test_output_has_no_trailing_newline():
    text = build_timeline([{"ts": T0, "text": "a"}], [], [], [])
    assert not text.endswith("\n")
