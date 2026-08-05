"""The DEL / GND / TWR wiring must keep emitting the keys the orchestrator reads.

``services/orchestrator_service/agent/tools/forward.py`` reads ``reply``,
``clearance_data`` and ``taxi_data`` off the agents' HTTP responses, and
``agents_evaluation/benchmark_agents.py`` also expects ``reply_data`` from TWR.
Those names, the ADK app names, the routes and the JSON keys the prompts promise
are a contract: this module pins them.

The agent packages cannot simply be imported here -- ``agents.del`` is not a legal
Python name (``del`` is a keyword) and each agent expects its own directory on
``sys.path`` (that is how its container runs). The configuration is therefore read
straight out of the source with ``ast``, which is enough because both runners and
apps are declared as plain literal ``CONFIG = ...(...)`` assignments.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_AGENTS_DIR = Path(__file__).resolve().parents[3] / "agents"


def _config_kwargs(path: Path) -> dict:
    """Return the keyword arguments of the module-level ``CONFIG = Call(...)``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "CONFIG" not in targets or not isinstance(node.value, ast.Call):
            continue
        return {kw.arg: _literal(kw.value) for kw in node.value.keywords}
    raise AssertionError(f"no module-level CONFIG assignment in {path}")


def _literal(node: ast.AST):
    """literal_eval, but rendering ``ContextField(...)`` calls as arg tuples."""
    if isinstance(node, ast.Call):
        return tuple(ast.literal_eval(a) for a in node.args)
    if isinstance(node, ast.Tuple):
        return tuple(_literal(e) for e in node.elts)
    return ast.literal_eval(node)


@pytest.fixture(scope="module")
def runner_configs() -> dict[str, dict]:
    return {a: _config_kwargs(_AGENTS_DIR / a / "runner.py") for a in ("del", "gnd", "twr")}


@pytest.fixture(scope="module")
def app_configs() -> dict[str, dict]:
    return {a: _config_kwargs(_AGENTS_DIR / a / "main.py") for a in ("del", "gnd", "twr")}


# ---------------------------------------------------------------------------
# Runner configuration
# ---------------------------------------------------------------------------

EXPECTED_RUNNERS = {
    "del": {
        "label": "DEL",
        "app_name": "airport_del",
        "text_key": "clearance_text",
        "data_key": "clearance_data",
        "context_fields": (
            ("flight_plan", "Flight plan: {value}"),
            ("atis", "ATIS: {value}"),
        ),
        "context_header": "\n\n[CONTEXT]",
    },
    "gnd": {
        "label": "GND",
        "app_name": "airport_gnd",
        "text_key": "instruction_text",
        "data_key": "taxi_data",
        "context_fields": (("clearance_data", "Clearance data: {value}"),),
        "context_header": "\n[CONTEXT]",
    },
    "twr": {
        "label": "TWR",
        "app_name": "airport_twr",
        "text_key": "reply_text",
        "data_key": "reply_data",
        "context_fields": (("clearance_data", "Clearance data: {value}"),),
        "context_header": "\n\n[CONTEXT]",
    },
}


@pytest.mark.parametrize("agent", sorted(EXPECTED_RUNNERS))
def test_runner_config_is_unchanged(runner_configs, agent):
    expected = dict(EXPECTED_RUNNERS[agent])
    actual = dict(runner_configs[agent])
    # ``context_header`` is defaulted in the dataclass; only GND overrides it.
    actual.setdefault("context_header", "\n\n[CONTEXT]")

    assert actual == expected


# ---------------------------------------------------------------------------
# FastAPI configuration
# ---------------------------------------------------------------------------

EXPECTED_APPS = {
    "del": {
        "label": "DEL",
        "role": "delivery",
        "title": "AIrport DEL Agent",
        "version": "0.2.0",
        "description": "ATC Delivery controller — issues IFR departure clearances",
        "data_key": "clearance_data",
        "context_fields": ("flight_plan", "atis"),
    },
    "gnd": {
        "label": "GND",
        "role": "ground",
        "title": "AIrport GND Agent",
        "version": "0.1.0",
        "description": "ATC Ground controller — issues pushback and taxi instructions",
        "data_key": "taxi_data",
        "context_fields": ("clearance_data",),
    },
    "twr": {
        "label": "TWR",
        "role": "tower",
        "title": "AIrport TWR Agent",
        "version": "0.1.0",
        "description": (
            "Pilot on Tower frequency — reads back lineup, takeoff and landing clearances"
        ),
        "data_key": "reply_data",
        "context_fields": ("clearance_data",),
    },
}


@pytest.mark.parametrize("agent", sorted(EXPECTED_APPS))
def test_app_config_is_unchanged(app_configs, agent):
    assert dict(app_configs[agent]) == EXPECTED_APPS[agent]


@pytest.mark.parametrize("agent", sorted(EXPECTED_APPS))
def test_runner_and_app_agree_on_the_data_key(runner_configs, app_configs, agent):
    assert runner_configs[agent]["data_key"] == app_configs[agent]["data_key"]


@pytest.mark.parametrize("agent", sorted(EXPECTED_APPS))
def test_app_context_fields_match_the_runner_ones(runner_configs, app_configs, agent):
    runner_names = tuple(name for name, _ in runner_configs[agent]["context_fields"])

    assert app_configs[agent]["context_fields"] == runner_names


@pytest.mark.parametrize("agent,port", [("del", "8080"), ("gnd", "8080"), ("twr", "8082")])
def test_uvicorn_default_port_is_unchanged(agent, port):
    source = (_AGENTS_DIR / agent / "main.py").read_text(encoding="utf-8")

    assert f'os.environ.get("PORT", "{port}")' in source
