"""
Root conftest.py for the AIrport test suite.

Responsibilities (executed once per pytest session, BEFORE any test module imports
project code):

1. Inject service paths into sys.path so `from db.models import ...`,
   `from core.arrival_planner import ...`, etc. resolve as the services
   themselves expect (they assume their own directory is on sys.path).
2. Patch sqlalchemy.dialects.postgresql.JSONB -> sqlalchemy.JSON so that
   ``Base.metadata.create_all`` works against an in-memory SQLite engine.
3. Install lightweight stubs in sys.modules for heavyweight external
   dependencies that would otherwise be imported transitively by project
   modules: XPPython3, google.adk.*, google.genai.types, influxdb_client.
4. Expose shared fixtures from tests/fixtures/* so they are auto-discovered.
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# 1) sys.path setup (must run before any project import)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ORCH_SVC = _REPO_ROOT / "services" / "orchestrator_service"
_ARR_SVC = _REPO_ROOT / "services" / "arrival_simulator_service"

for _p in (_REPO_ROOT, _ORCH_SVC, _ARR_SVC):
    sp = str(_p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

# ---------------------------------------------------------------------------
# 2) Patch JSONB -> JSON so SQLite can host the AircraftClearance table
# ---------------------------------------------------------------------------

try:
    import sqlalchemy
    import sqlalchemy.dialects.postgresql as _pg_dialect

    if not hasattr(_pg_dialect.JSONB, "_airport_test_patched"):
        _pg_dialect.JSONB = sqlalchemy.JSON  # type: ignore[assignment]
        sqlalchemy.JSON._airport_test_patched = True  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - sqlalchemy is a hard dep
    pass

# ---------------------------------------------------------------------------
# 3) Stub heavyweight external modules
# ---------------------------------------------------------------------------


def _install_stub(name: str, attrs: dict | None = None) -> types.ModuleType:
    """Insert (or return) a stub module under ``name`` in sys.modules."""
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    if attrs:
        for k, v in attrs.items():
            setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# --- XPPython3 (only relevant for xplane_plugin tests) ------------------------
_xp_mod = _install_stub("XPPython3")
_xp_attr = _install_stub("XPPython3.xp")
_xp_mod.xp = _xp_attr  # so `from XPPython3 import xp` resolves

# Common functions used across the plugin -- return innocuous defaults
for _name in (
    "createProbe",
    "destroyProbe",
    "worldToLocal",
    "localToWorld",
    "probeTerrainXYZ",
    "createInstance",
    "destroyInstance",
    "instanceSetPosition",
    "createFlightLoop",
    "destroyFlightLoop",
    "scheduleFlightLoop",
    "log",
    "sys_log",
    "getDataf",
    "getDatai",
    "getDatad",
    "findDataRef",
    "getString",
    "loadObject",
    "unloadObject",
):
    setattr(_xp_attr, _name, MagicMock(name=f"xp.{_name}"))


# --- google.adk.* and google.genai.types --------------------------------------
_install_stub("google")
_install_stub("google.adk")

_adk_runners = _install_stub("google.adk.runners")


class _StubRunner:
    """Minimal stand-in for google.adk.runners.Runner.

    Tests that need behavior should patch ``runner.Runner`` with their own
    ``FakeADKRunner`` (see tests/fixtures/adk_runner.py).
    """

    def __init__(self, *_, **__):  # noqa: D401
        pass

    async def run_async(self, *_, **__):  # pragma: no cover - patched in tests
        if False:
            yield None


_adk_runners.Runner = _StubRunner

_adk_sessions = _install_stub("google.adk.sessions")


class _StubInMemorySessionService:
    def __init__(self):
        self._sessions: dict = {}

    async def create_session(self, app_name: str, user_id: str, session_id: str, state=None):  # noqa: D401
        sess = types.SimpleNamespace(
            app_name=app_name, user_id=user_id, id=session_id, state=dict(state or {})
        )
        self._sessions[(app_name, user_id, session_id)] = sess
        return sess

    async def get_session(self, app_name: str, user_id: str, session_id: str):  # noqa: D401
        return self._sessions.get((app_name, user_id, session_id))


_adk_sessions.InMemorySessionService = _StubInMemorySessionService

_adk_agents = _install_stub("google.adk.agents")


class _StubAgent:
    def __init__(self, *_, **kw):
        self.name = kw.get("name", "stub")
        self.model = kw.get("model")
        self.description = kw.get("description")
        self.instruction = kw.get("instruction")
        self.tools = kw.get("tools", [])


_adk_agents.Agent = _StubAgent
_adk_agents.LlmAgent = _StubAgent

_adk_tools = _install_stub("google.adk.tools")


class _StubToolContext:
    def __init__(self, state=None):
        self.state = state if state is not None else {}


_adk_tools.ToolContext = _StubToolContext

_genai = _install_stub("google.genai")
_genai_types = _install_stub("google.genai.types")


class _StubPart:
    def __init__(self, text: str = "", **_):
        self.text = text

    @classmethod
    def from_text(cls, text: str):
        return cls(text=text)


class _StubContent:
    def __init__(self, role: str = "user", parts=None):
        self.role = role
        self.parts = parts or []


_genai_types.Part = _StubPart
_genai_types.Content = _StubContent

_adk_callbacks = _install_stub("google.adk.agents.callback_context")


class _StubCallbackContext:
    def __init__(self, state=None):
        self.state = state if state is not None else {}


_adk_callbacks.CallbackContext = _StubCallbackContext


# --- shared.callbacks (lives inside services/orchestrator_service/shared, but
#     the repo root has its own `shared/` package which gets imported first,
#     so `from shared.callbacks import log_before, log_after` fails. Provide
#     no-op stubs to break the ambiguity for tests.) -----------------------
_shared_callbacks = _install_stub(
    "shared.callbacks",
    {
        "log_before": lambda *a, **kw: None,
        "log_after": lambda *a, **kw: None,
    },
)


# --- influxdb_client (used by shared/services/aircraft_state_store) -----------
_influx = _install_stub("influxdb_client")
_influx.InfluxDBClient = MagicMock(name="InfluxDBClient")
_influx.Point = MagicMock(name="Point")
_influx.WritePrecision = types.SimpleNamespace(NS="ns", MS="ms", S="s")
_install_stub("influxdb_client.client", {"write_api": types.SimpleNamespace(SYNCHRONOUS=object())})
_install_stub(
    "influxdb_client.client.write_api",
    {"SYNCHRONOUS": object(), "ASYNCHRONOUS": object()},
)


# ---------------------------------------------------------------------------
# 4) Re-export fixtures so they are auto-discovered by pytest
# ---------------------------------------------------------------------------

# Make sure os.environ does not point to real services during tests
os.environ.setdefault("POSTGRES_HOST", "127.0.0.1")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "airport_test")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("REDIS_HOST", "127.0.0.1")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("AGENT_MODEL", "stub-model")

# Fixtures live in tests/fixtures/* and are loaded via pytest_plugins so they
# are usable from every test module without explicit imports.
pytest_plugins = [
    "tests.fixtures.fake_db",
    "tests.fixtures.fake_redis",
]
