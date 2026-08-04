"""Isolated import of weather_service modules for the tests in this package.

Import `atis_generator` from here rather than reaching for `sys.path`::

    from tests.weather._weather_service_import import atis_generator


`weather_service` and `arrival_simulator_service` both ship top-level packages
named `core`, and each service assumes its own directory sits on `sys.path`
(that is how they run inside their containers). The `sys.path` shim that
`tests/arrivals/conftest.py` uses therefore cannot be repeated here: whichever
service lands on the path first wins, and `from core.arrival_planner import ...`
and `from core.metar_taf_fetcher import ...` cannot both resolve in one session.

So weather_service's modules are loaded from their file paths instead, with
`core` and `models` aliased only for the duration of the load and restored
afterwards. Nothing leaks into `sys.modules`, and the arrivals tests keep the
`core` they expect. Coverage still attributes the lines correctly, because it
keys on file paths rather than module names.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_SVC = Path(__file__).resolve().parents[2] / "services" / "weather_service"

# Top-level names weather_service occupies while it is being imported. Anything
# already bound to them is put back once the load finishes.
_BORROWED = ("core", "core.atis_generator", "core.metar_taf_fetcher", "models", "models.schemas")


def _exec_from_path(module_name: str, path: Path) -> types.ModuleType:
    """Import `path` under `module_name`, registering it before execution.

    Registering first is what lets `atis_generator` resolve its own
    `from core.metar_taf_fetcher import get_metar` against the module already
    placed in `sys.modules` rather than searching `sys.path` again.
    """
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_atis_generator() -> types.ModuleType:
    saved = {name: sys.modules.get(name) for name in _BORROWED}
    try:
        for pkg_name, pkg_dir in (("core", _SVC / "core"), ("models", _SVC / "models")):
            package = types.ModuleType(pkg_name)
            package.__path__ = [str(pkg_dir)]
            sys.modules[pkg_name] = package

        _exec_from_path("models.schemas", _SVC / "models" / "schemas.py")
        _exec_from_path("core.metar_taf_fetcher", _SVC / "core" / "metar_taf_fetcher.py")
        return _exec_from_path("core.atis_generator", _SVC / "core" / "atis_generator.py")
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


atis_generator = _load_atis_generator()
