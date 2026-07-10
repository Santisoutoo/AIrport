# Wiki Maintenance

This wiki is **generated** — never edit pages in the GitHub Wiki UI; they get overwritten on
the next publish.

## The pipeline

```
openwiki/  ──►  scripts/build_wiki.py  ──►  wiki/  ──►  GitHub Wiki
(source,        (flattens page names,       (generated,   (published by
 in the repo)    rewrites links,             gitignored)   publish-wiki.yml)
                 builds _Sidebar.md)
```

- [`openwiki/`](../../openwiki/) is the **only source of truth**. Guides live in
  [`openwiki/guides/`](../../openwiki/guides/) and are **hand-written**; the module/reference
  pages are maintained by the `openwiki-writer` agent.
- [`scripts/build_wiki.py`](../../scripts/build_wiki.py) flattens each page to a wiki page
  name (`guides/installation.md` → `Installation`), rewrites relative links to wiki-page
  links or absolute GitHub URLs, and generates `Home.md` + the sectioned `_Sidebar.md`.
- `wiki/` is the build output — **gitignored**, rebuilt on every publish.
- [`.github/workflows/publish-wiki.yml`](../../.github/workflows/publish-wiki.yml)
  (manual, `workflow_dispatch`) runs the build on the default branch and force-syncs the
  result into the `<repo>.wiki.git` repository.

## Editing pages

| You want to… | Do this |
|---|---|
| Fix or extend a **guide** | Edit `openwiki/guides/<page>.md` by hand, commit, run the publish workflow |
| Refresh the **module/reference pages** after code changes | Run the `/update-docs` command (or the manual `openwiki-update.yml` workflow, which opens a PR) — it runs the `openwiki-writer` agent incrementally from git changes |
| Add a **new page** | Create the `.md` under `openwiki/` (guides go in `guides/`); if it should appear in the sidebar, add its page name to `SIDEBAR_SECTIONS` in `scripts/build_wiki.py` |
| Rename a page | Prefer not to — wiki URLs break; if you must, adjust `EXPLICIT_PAGE_NAMES`/`SIDEBAR_SECTIONS` accordingly |

The `openwiki-writer` agent is instructed never to touch `openwiki/guides/`.

## Preview locally

```bash
python scripts/build_wiki.py
# inspect wiki/_Sidebar.md and the generated pages
```

## Publish

Run the **Publish Wiki** workflow from the GitHub Actions tab (or
`gh workflow run publish-wiki.yml`). It commits `docs: sync wiki from openwiki/` to the
wiki repository.

## Related

[Home](../index.md) · [System Overview](system-overview.md)
