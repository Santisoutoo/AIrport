"""Vendor agents/common/*.py into every agent's local ``shared/`` package.

Each pilot agent is deployed on its own with
``gcloud run deploy <x>-agent --source agents/<x>``, so the Docker build context is
that single agent directory (``COPY . .``). Code shared between the agents therefore
has to physically live inside each of them -- the same convention
``shared/callbacks.py`` already follows.

``agents/common/`` is the single source of truth; this script copies it into
``agents/<phase>/shared/``. ``tests/unit/agents/test_agent_common_vendoring.py``
fails the suite if the copies ever drift.

Usage::

    python scripts/sync_agent_common.py           # write the copies
    python scripts/sync_agent_common.py --check   # exit 1 if out of date
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMON_DIR = REPO_ROOT / "agents" / "common"
AGENTS = ("del", "gnd", "twr")

# Modules vendored into every agent. ``callbacks.py`` is intentionally absent:
# each agent keeps its own, tuned to that position's state field names.
VENDORED_MODULES = ("agent_runner.py", "agent_app.py")


def vendored_path(agent: str, module: str) -> Path:
    return REPO_ROOT / "agents" / agent / "shared" / module


def sync(check_only: bool = False) -> int:
    stale: list[Path] = []
    for module in VENDORED_MODULES:
        source = COMMON_DIR / module
        if not source.is_file():
            print(f"missing source module: {source}", file=sys.stderr)
            return 1
        for agent in AGENTS:
            target = vendored_path(agent, module)
            if target.is_file() and target.read_bytes() == source.read_bytes():
                continue
            if check_only:
                stale.append(target)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            print(f"updated {target.relative_to(REPO_ROOT)}")

    if stale:
        print("vendored copies are out of date:", file=sys.stderr)
        for path in stale:
            print(f"  {path.relative_to(REPO_ROOT)}", file=sys.stderr)
        print("run: python scripts/sync_agent_common.py", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write anything; exit 1 if a vendored copy is out of date",
    )
    args = parser.parse_args()
    return sync(check_only=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
