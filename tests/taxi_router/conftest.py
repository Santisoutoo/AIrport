"""Shared fixtures for the taxi_router test suite.

Provides:
  - `airport`: parametrised fixture yielding one `AirportFixture` per ICAO.
    Tests using it run once per airport (currently LEST and LEIB).
  - `lest_graph`, `leib_graph`: airport-specific fixtures used by tests that
    need exact counts or behaviours only present in one airport.
  - `lest_raw_data`, `leib_raw_data`, `lest_json_path`, `leib_json_path`:
    auxiliary fixtures for tests that read the JSON directly as an oracle.
"""
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from plugins.GND.graph import AirportGraph

BASE = Path(__file__).resolve().parents[2] / "data" / "airport_data"

LEST_JSON = BASE / "LEST" / "LEST_graph.json"
LEIB_JSON = BASE / "LEIB" / "LEIB_graph.json"


@dataclass(frozen=True)
class AirportFixture:
    """Metadata + loaded graph for a single airport used in parametrised tests.

    Attributes:
        icao: ICAO designator (e.g. "LEST").
        graph: a built AirportGraph instance.
        raw_data: the parsed JSON dict the graph was built from.
        expected_taxiway_subset: a subset of taxiway designators that must be
            present in `_nodes_by_taxiway`.
        expected_runway_ids: set of runway-end designators that must be in
            `_runways_by_id` (e.g. {"17","35"}).
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


_LEST_META = dict(
    expected_taxiway_subset={
        "D1", "D2", "D3", "D4", "E1", "E2", "E3", "E4",
        "R", "T", "Y", "Z",
    },
    expected_runway_ids={"17", "35"},
    non_numeric_stand_substr="Mil 5",
    sample_repeated_name="D3_stop",
)
_LEIB_META = dict(
    expected_taxiway_subset={
        "A", "B", "C", "D", "E", "F", "G", "H1", "H2", "H3", "H4", "I", "K",
    },
    expected_runway_ids={"06", "24"},
    non_numeric_stand_substr="19A",
    sample_repeated_name=None,  # LEIB nodes have no useful repeated names
)


@pytest.fixture(scope="session", params=["LEST", "LEIB"])
def airport(request):
    """Parametrised airport fixture: runs each consuming test once per ICAO."""
    icao = request.param
    if icao == "LEST":
        return _load_airport("LEST", LEST_JSON, **_LEST_META)
    return _load_airport("LEIB", LEIB_JSON, **_LEIB_META)


# ---- Airport-specific fixtures (single-airport tests) ----------------------

@pytest.fixture(scope="session")
def lest_graph():
    return AirportGraph(str(LEST_JSON))


@pytest.fixture(scope="session")
def leib_graph():
    return AirportGraph(str(LEIB_JSON))


@pytest.fixture(scope="session")
def lest_raw_data():
    return json.loads(LEST_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def leib_raw_data():
    return json.loads(LEIB_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def lest_json_path():
    return str(LEST_JSON)


@pytest.fixture(scope="session")
def leib_json_path():
    return str(LEIB_JSON)
