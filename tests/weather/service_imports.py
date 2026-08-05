"""Isolated importer for ``services/weather_service`` modules.

The weather service assumes its own directory is on ``sys.path`` (it imports
``api.*``, ``core.*`` and ``models.*`` as top-level packages), exactly like the
other services in this repo. Those package names collide with
``services/orchestrator_service`` (``api``) and
``services/arrival_simulator_service`` (``core``), both of which are already on
``sys.path`` when the full suite runs.

To keep the suites independent, the weather modules are imported here inside a
context that temporarily takes over those names and restores whatever was there
before. Nothing leaks into ``sys.path`` or ``sys.modules`` once this module
finishes importing.

Everything is imported inside a *single* context so that, for example, the
``WeatherUpstreamError`` seen by the tests is the very same class object the API
layer catches.
"""

from __future__ import annotations

import importlib
import os
import sys
from contextlib import contextmanager
from pathlib import Path

_SVC = Path(__file__).resolve().parents[2] / "services" / "weather_service"

#: Top-level package names the weather service expects to own.
_OWNED_ROOTS = ("api", "core", "models")

#: ``core.database.connection`` builds the SQLAlchemy URL at import time from
#: these variables. The engine is lazy, so no connection is ever attempted.
_DB_ENV_DEFAULTS = {
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "weather_test",
    "POSTGRES_USER": "test",
    "POSTGRES_PASSWORD": "test",
}


def _owned(module_name: str) -> bool:
    return module_name.split(".")[0] in _OWNED_ROOTS


@contextmanager
def _weather_service_on_path():
    """Temporarily make ``services/weather_service`` the owner of its package names."""
    saved_path = list(sys.path)
    saved_modules = {name: mod for name, mod in list(sys.modules.items()) if _owned(name)}
    saved_env = {key: os.environ.get(key) for key in _DB_ENV_DEFAULTS}

    for name in saved_modules:
        del sys.modules[name]
    for key, value in _DB_ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)

    sys.path.insert(0, str(_SVC))
    try:
        yield
    finally:
        sys.path[:] = saved_path
        for name in [n for n in list(sys.modules) if _owned(n)]:
            del sys.modules[name]
        sys.modules.update(saved_modules)
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


with _weather_service_on_path():
    # ``api.routes`` transitively imports every other module we need, so a
    # single pass keeps all of them consistent with each other.
    routes = importlib.import_module("api.routes")
    metar_taf_fetcher = importlib.import_module("core.metar_taf_fetcher")
    atis_generator = importlib.import_module("core.atis_generator")
    schemas = importlib.import_module("models.schemas")

ATISGenerator = atis_generator.ATISGenerator
CloudLayer = schemas.CloudLayer
NoWeatherDataError = metar_taf_fetcher.NoWeatherDataError
WeatherUpstreamError = metar_taf_fetcher.WeatherUpstreamError
get_metar = metar_taf_fetcher.get_metar
get_taf = metar_taf_fetcher.get_taf

__all__ = [
    "ATISGenerator",
    "CloudLayer",
    "NoWeatherDataError",
    "WeatherUpstreamError",
    "atis_generator",
    "get_metar",
    "get_taf",
    "metar_taf_fetcher",
    "routes",
    "schemas",
]
