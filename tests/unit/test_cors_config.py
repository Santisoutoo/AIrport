"""Regression test for issue #61: no service may pair a wildcard CORS origin
with allow_credentials=True (invalid per the CORS spec, and Starlette's
workaround for it lets any origin call the API with credentials).

This scans each service's main.py source rather than importing the modules
directly: weather_service and flight_plan_service run live DB calls
(Base.metadata.create_all, a raw ALTER TABLE check) at import time, not in
their FastAPI lifespan, so importing them requires a real Postgres
connection that isn't available in the unit test environment.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

SERVICE_MAIN_FILES = [
    _REPO_ROOT / "services" / "orchestrator_service" / "main.py",
    _REPO_ROOT / "services" / "controller_hmi_service" / "main.py",
    _REPO_ROOT / "services" / "asr_service" / "main.py",
    _REPO_ROOT / "services" / "weather_service" / "main.py",
    _REPO_ROOT / "services" / "flight_plan_service" / "main.py",
    _REPO_ROOT / "services" / "arrival_simulator_service" / "main.py",
]


def _find_cors_middleware_call(tree: ast.Module) -> ast.Call | None:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_middleware"
            and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "CORSMiddleware"
        ):
            return node
    return None


def _keyword_value(call: ast.Call, name: str):
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


@pytest.mark.parametrize("main_py", SERVICE_MAIN_FILES, ids=lambda p: p.parent.name)
def test_no_wildcard_origin_with_credentials(main_py: Path):
    assert main_py.exists(), f"expected service entrypoint at {main_py}"
    tree = ast.parse(main_py.read_text(encoding="utf-8"), filename=str(main_py))

    call = _find_cors_middleware_call(tree)
    assert call is not None, f"{main_py} does not configure CORSMiddleware"

    allow_origins = _keyword_value(call, "allow_origins")
    assert allow_origins is not None, f"{main_py}: CORSMiddleware missing allow_origins"

    is_wildcard_literal = (
        isinstance(allow_origins, ast.List)
        and len(allow_origins.elts) == 1
        and isinstance(allow_origins.elts[0], ast.Constant)
        and allow_origins.elts[0].value == "*"
    )
    assert not is_wildcard_literal, (
        f"{main_py}: allow_origins is hardcoded to ['*'] combined with allow_credentials — "
        "must come from config (e.g. the CORS_ORIGINS env var)"
    )
