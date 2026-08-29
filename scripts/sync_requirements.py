#!/usr/bin/env python3
"""Generate the per-service ``requirements.txt`` files from ``pyproject.toml``.

The root ``pyproject.toml`` is the single source of truth for dependencies
(issue #62). Each deployable unit maps to a list of extras declared under
``[project.optional-dependencies]``; the ``requirements.txt`` its Dockerfile
installs is generated from that list, so the pinning policy lives in exactly
one place.

Usage::

    python scripts/sync_requirements.py            # rewrite the files
    python scripts/sync_requirements.py --check    # fail if any file is stale

The ``--check`` mode runs in CI so a change to ``pyproject.toml`` that is not
propagated to the service images is caught at review time.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"

# Deployable unit -> extras installed in its image, in order. Every service
# image gets the shared FastAPI stack (`service-core`) plus its own extra.
SERVICES: dict[str, list[str]] = {
    "agents/del": ["service-core", "agents"],
    "agents/gnd": ["service-core", "agents"],
    "agents/twr": ["service-core", "agents"],
    "services/arrival_simulator_service": ["service-core", "arrival-simulator"],
    "services/asr_service": ["service-core", "asr"],
    "services/controller_hmi_service": ["service-core", "controller-hmi"],
    "services/flight_plan_service": ["service-core", "flight-plan"],
    "services/orchestrator_service": ["service-core", "orchestrator"],
    "services/pilots_communication": ["service-core", "pilots-communication"],
    "services/weather_service": ["service-core", "weather"],
}

HEADER = """\
# GENERATED FILE -- DO NOT EDIT.
#
# Source of truth: root pyproject.toml, extras: {extras}
# Regenerate with: python scripts/sync_requirements.py
"""


def load_extras() -> dict[str, list[str]]:
    """Return ``[project.optional-dependencies]`` from the root pyproject."""
    with PYPROJECT.open("rb") as handle:
        data = tomllib.load(handle)
    return data["project"]["optional-dependencies"]


def render(extras: dict[str, list[str]], names: list[str]) -> str:
    """Render the requirements file body for one service."""
    seen: dict[str, None] = {}
    for name in names:
        if name not in extras:
            raise SystemExit(f"pyproject.toml has no extra named '{name}'")
        for requirement in extras[name]:
            seen.setdefault(requirement, None)
    body = "\n".join(seen)
    return HEADER.format(extras=", ".join(names)) + "\n" + body + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit non-zero if a generated file is out of date",
    )
    args = parser.parse_args()

    extras = load_extras()
    stale: list[str] = []

    for service, names in SERVICES.items():
        target = REPO_ROOT / service / "requirements.txt"
        expected = render(extras, names)
        current = target.read_text(encoding="utf-8") if target.exists() else None
        if current == expected:
            continue
        if args.check:
            stale.append(service)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(expected, encoding="utf-8", newline="\n")
        print(f"wrote {service}/requirements.txt")

    if stale:
        print("Out of date with pyproject.toml:", file=sys.stderr)
        for service in stale:
            print(f"  {service}/requirements.txt", file=sys.stderr)
        print(
            "Run `python scripts/sync_requirements.py` and commit the result.",
            file=sys.stderr,
        )
        return 1

    if args.check:
        print("All service requirements.txt files are in sync.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
