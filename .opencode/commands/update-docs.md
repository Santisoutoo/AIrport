---
description: Generate or refresh the openwiki/ agent-facing documentation using the openwiki-writer subagent.
agent: openwiki-writer
---

Use the **openwiki-writer** subagent to generate or refresh the repository documentation under
`openwiki/`.

- If `openwiki/.last-update.json` does not exist, do a full generation of the wiki.
- If it exists, do an incremental update: diff `last_commit..HEAD` and refresh only the pages
  affected by changed files, then bump `openwiki/.last-update.json`.

Also ensure the `openwiki/` pointer sections in `CLAUDE.md` and `AGENTS.md` are present.

Do not commit or push — leave the changes in the working tree for review.
