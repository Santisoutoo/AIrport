"""Shared fixtures for the taxi_router test suite.

Provides:
  - `airport`: parametrised fixture yielding one `AirportFixture` per ICAO.
    Tests using it run once per airport (currently LEBL).
  - `lebl_graph`: airport-specific fixture used by tests that need exact
    behaviours of a single airport.
  - `lebl_json_path`: auxiliary fixture for the test that builds straight
    from the JSON file path.

The graph data (`data/airport_data/LEBL/LEBL_graph.json`) is committed as a
CI test fixture; it is generated from `LEBL.dat` via
`python -m plugins.GND.data_parser LEBL`.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from plugins.GND.graph import AirportGraph

BASE = Path(__file__).resolve().parents[2] / "data" / "airport_data"

LEBL_JSON = BASE / "LEBL" / "LEBL_graph.json"


@dataclass(frozen=True)
class AirportFixture:
    """Metadata + loaded graph for a single airport used in parametrised tests.

    Attributes:
        icao: ICAO designator (e.g. "LEBL").
        graph: a built AirportGraph instance.
        raw_data: the parsed JSON dict the graph was built from.
        expected_taxiway_subset: a subset of taxiway designators that must be
            present in `_nodes_by_taxiway`.
        expected_runway_ids: set of runway-end designators that must be in
            `_runways_by_id` (e.g. {"02","06L"}).
        non_numeric_stand_substr: a stand_id substring that is *not* a node_id
            and therefore exercises step 3 of resolve_point. Used by the stand
            resolution test.
        sample_repeated_name: a node name that appears multiple times in the
            graph (used for hint-disambiguation). None when no useful repeated
            name exists in this airport.
    """

    icao: str
    graph: AirportGraph
    raw_data: dict
    expected_taxiway_subset: set
    expected_runway_ids: set
    non_numeric_stand_substr: str
    sample_repeated_name: str | None


def _load_airport(icao: str, json_path: Path, **meta) -> AirportFixture:
    raw = json.loads(json_path.read_text(encoding="utf-8"))
    return AirportFixture(
        icao=icao,
        graph=AirportGraph(data=raw),
        raw_data=raw,
        **meta,
    )


_LEBL_META = dict(
    expected_taxiway_subset={
        "B",
        "D",
        "E",
        "J",
        "K",
        "L",
        "M",
        "N",
        "Q",
        "S",
    },
    expected_runway_ids={"02", "06L"},
    non_numeric_stand_substr="157A",
    sample_repeated_name="_stop",
)


@pytest.fixture(scope="session", params=["LEBL"])
def airport(request):
    """Parametrised airport fixture: runs each consuming test once per ICAO."""
    return _load_airport("LEBL", LEBL_JSON, **_LEBL_META)


# ---- Airport-specific fixtures (single-airport tests) ----------------------


@pytest.fixture(scope="session")
def lebl_graph():
    return AirportGraph(str(LEBL_JSON))


@pytest.fixture(scope="session")
def lebl_json_path():
    return str(LEBL_JSON)
