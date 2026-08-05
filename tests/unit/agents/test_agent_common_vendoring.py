"""The vendored copies of agents/common/ must not drift.

Each pilot agent is built from its own directory (``gcloud run deploy --source
agents/<phase>``, ``COPY . .``), so the shared modules physically live inside every
agent under ``shared/``. ``agents/common/`` is the single source of truth and
``scripts/sync_agent_common.py`` copies it; this test is the guard that keeps the
copies honest.
"""

from __future__ import annotations

import pytest

from scripts.sync_agent_common import AGENTS, COMMON_DIR, VENDORED_MODULES, sync, vendored_path


@pytest.mark.parametrize("agent", AGENTS)
@pytest.mark.parametrize("module", VENDORED_MODULES)
def test_vendored_copy_matches_the_source_of_truth(agent, module):
    source = COMMON_DIR / module
    target = vendored_path(agent, module)

    assert target.is_file(), f"{target} is missing — run scripts/sync_agent_common.py"
    assert target.read_bytes() == source.read_bytes(), (
        f"{target} drifted from agents/common/{module} — edit agents/common/ and run scripts/sync_agent_common.py"
    )


def test_sync_check_mode_passes():
    assert sync(check_only=True) == 0


@pytest.mark.parametrize("agent", AGENTS)
def test_agents_import_the_vendored_module_not_the_repo_shared_package(agent):
    """Inside the container the agent directory is the import root.

    ``from shared.agent_runner import ...`` therefore resolves to the vendored copy,
    not to the repo-root ``shared/`` package (which is not in the build context).
    """
    for filename in ("runner.py", "main.py"):
        source = (COMMON_DIR.parent / agent / filename).read_text(encoding="utf-8")
        assert "from shared.agent_" in source
        assert "agents.common" not in source
