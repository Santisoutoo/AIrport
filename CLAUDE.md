# AIrport — Project Instructions

## Language

Everything in this repo is written in **English**, regardless of the language used in
conversation:

- Code: identifiers, comments, docstrings, log messages.
- Git: commit messages, branch names.
- GitHub: issue and PR titles and bodies, labels, milestones, reviews.
- Documentation: `docs/`, `openwiki/`, READMEs.

## Documentation (openwiki)

This repo has agent-facing documentation under [`openwiki/`](openwiki/) — structured markdown
optimized for finding repo context fast (architecture, services, agents, shared, X-Plane,
testing). **Consult [`openwiki/index.md`](openwiki/index.md) first** when you need to understand
how the codebase fits together. Human-facing docs live in [`docs/`](docs/).

Refresh the wiki with the `/update-docs` command (runs the `openwiki-writer` agent on Claude
Sonnet). It updates incrementally from git changes; see
[`.claude/agents/openwiki-writer.md`](.claude/agents/openwiki-writer.md).
