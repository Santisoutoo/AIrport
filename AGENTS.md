# AGENTS.md

Guidance for coding agents working in the **AIrport** repository.

## Documentation (openwiki)

This repo has agent-facing documentation under [`openwiki/`](openwiki/) — structured markdown
optimized for finding repo context fast: architecture, per-service pages, the DEL/GND/TWR agents,
the shared package, X-Plane integration, and testing.

**Consult [`openwiki/index.md`](openwiki/index.md) first** when you need to understand how the
codebase fits together, before grepping around. Human-facing docs live in [`docs/`](docs/).

## Keeping docs current

Refresh the wiki with the `/update-docs` slash command, which runs the `openwiki-writer` agent.
Available from both OpenCode (`.opencode/agents/openwiki-writer.md`) and Claude Code
(`.claude/agents/openwiki-writer.md`). It updates incrementally from git changes since the last run
(tracked in [`openwiki/.last-update.json`](openwiki/.last-update.json)). A manual GitHub Action
([`.github/workflows/openwiki-update.yml`](.github/workflows/openwiki-update.yml)) can also open a
docs-update PR on demand.
