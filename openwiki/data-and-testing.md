# Data, evaluation & testing

Airport data, agent/WER evaluation, and the pytest suite. See [index](index.md).

## `data/` — airport data & scripts

| Path | Role |
|---|---|
| [`data/airport_data/LEBL/`](../data/airport_data/) | Barcelona (LEBL) airport data — taxiways, stands, graph inputs |
| [`data/scripts/airport_data_fetcher.py`](../data/scripts/airport_data_fetcher.py) | Fetches raw airport data |
| [`data/scripts/airport_graph_builder.py`](../data/scripts/airport_graph_builder.py) | Builds the taxiway graph consumed by [taxi_router](shared.md) |
| [`data/notebooks/visualization.ipynb`](../data/notebooks/) | Visualization notebook |

Plotting/analysis utilities live under [`scripts/`](../scripts/): `plot_airport_routes.py`,
`plot_agent_benchmark.py`, `analyze_pipeline_log.py`, `plot_lest_*`, `overlay_lest_routes_on_image.py`.

## `agents_evaluation/` — agent & WER benchmarks

| Path | Role |
|---|---|
| [`benchmark_agents.py`](../agents_evaluation/benchmark_agents.py) | Benchmarks the DEL/GND/TWR [agents](agents.md) |
| [`validate_agents.py`](../agents_evaluation/validate_agents.py) | Validates agent responses |
| [`evaluate_wer.py`](../agents_evaluation/evaluate_wer.py) | Word Error Rate for [ASR](services/asr_service.md) (uses `jiwer`) |
| [`corpus_wer/`](../agents_evaluation/corpus_wer/) | Phase-specific corpora (`del` / `gnd` / `twr`) + [README](../agents_evaluation/corpus_wer/README.md) |
| `output/` | Benchmark results (CSV) |

## `tests/` — pytest suite

Config in [`pyproject.toml`](../pyproject.toml) (`[tool.pytest.ini_options]`): `asyncio_mode = auto`,
`testpaths = ["tests"]`, coverage `fail_under = 70`. `pythonpath` includes the orchestrator and
arrival_simulator service roots so their modules import bare in tests.

| Area | Path | Covers |
|---|---|---|
| Departure/arrival e2e | [`tests/integration/`](../tests/integration/) | `test_departure_pipeline.py`, `test_arrival_pipeline.py` |
| Orchestrator units | [`tests/unit/orchestrator/`](../tests/unit/orchestrator/) | dispatch, advance tools, arrivals endpoint, events subscriber, forward tool, frequency audit, repository, runner, session log |
| Arrival simulator units | [`tests/unit/arrival_simulator/`](../tests/unit/arrival_simulator/) | event bridge |
| Taxi routing | [`tests/taxi_router/`](../tests/taxi_router/) | graph construction, token resolution, routing e2e, pushback leg, HMI chat |
| Arrivals | [`tests/arrivals/`](../tests/arrivals/) | phases, runway config, arrival planner, geo |
| Debrief | [`tests/debrief/`](../tests/debrief/) | debrief builder |
| Fixtures | [`tests/fixtures/`](../tests/fixtures/) | `fake_db.py`, `fake_redis.py`, `adk_runner.py` |

Run: `uv run pytest` (or `pytest`). Coverage source/omit lists are in `[tool.coverage.run]`.

## Related
[index](index.md) · [agents](agents.md) · [orchestrator](services/orchestrator_service.md) · [shared](shared.md)
