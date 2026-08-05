#!/usr/bin/env python3
"""Build GitHub-Wiki-ready markdown from the openwiki/ folder.

The GitHub Wiki is a *separate* git repo (`<repo>.wiki.git`) with a flat page
namespace, so it cannot use openwiki's relative links to source files or its
`services/` subfolder. This script:

  * flattens each openwiki page to a single wiki page name (e.g.
    `services/orchestrator_service.md` -> `Service-Orchestrator.md`),
  * rewrites links between wiki pages to wiki page names,
  * rewrites links that point at repo files/dirs (code, docs, configs) to
    absolute GitHub URLs (`.../blob/<ref>/...` or `.../tree/<ref>/...`),
  * generates `Home.md` (from index.md) and a `_Sidebar.md` nav.

Output goes to `--out` (default `wiki/`). Run locally to preview, or in CI
(`.github/workflows/publish-wiki.yml`) to publish.

Usage:
    python scripts/build_wiki.py --src openwiki --out wiki \
        --repo Santisoutoo/AIrport --ref main
"""

from __future__ import annotations

import argparse
import os
import re
import sys

LINK_RE = re.compile(r"(!?)\[([^\]]*)\]\(([^)]+)\)")

EXPLICIT_PAGE_NAMES = {
    "index.md": "Home",
    "architecture.md": "Architecture",
    "agents.md": "Agents",
    "shared.md": "Shared",
    "xplane.md": "X-Plane",
    "data-and-testing.md": "Data-and-Testing",
    "guides/faq.md": "FAQ",
    "guides/xplane-plugin-setup.md": "X-Plane-Plugin-Setup",
}

# Sidebar layout: (section title, ordered page names). Service-* pages are
# appended to "Modules"; any page not covered lands at the end of "Internals".
SIDEBAR_SECTIONS = [
    (
        "Getting Started",
        ["Home", "Quickstart", "Installation", "Cloud-Agents-Deployment", "X-Plane-Plugin-Setup", "Configuration"],
    ),
    ("Help", ["Troubleshooting", "FAQ"]),
    ("Modules", ["System-Overview", "Agents", "Shared", "X-Plane"]),
    ("Internals", ["Architecture", "Data-and-Testing", "Wiki-Maintenance"]),
]


def page_name_for(rel: str) -> str:
    """Map an openwiki-relative md path to a flat wiki page name (no .md)."""
    rel = rel.replace(os.sep, "/")
    if rel in EXPLICIT_PAGE_NAMES:
        return EXPLICIT_PAGE_NAMES[rel]
    parts = rel.split("/")
    if parts[0] == "services" and len(parts) == 2:
        name = parts[1][:-3] if parts[1].endswith(".md") else parts[1]
        if name.endswith("_service"):
            name = name[: -len("_service")]
        words = [w for w in name.replace("_", "-").split("-") if w]
        return "Service-" + "-".join(w.capitalize() for w in words)
    base = parts[-1][:-3] if parts[-1].endswith(".md") else parts[-1]
    words = [w for w in base.replace("_", "-").split("-") if w]
    return "-".join(w.capitalize() for w in words)


def discover_pages(src: str) -> dict[str, str]:
    """Return {openwiki-relative-posix-md-path: wiki page name}."""
    pages: dict[str, str] = {}
    for root, _dirs, files in os.walk(src):
        for f in files:
            if not f.endswith(".md"):
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, src).replace(os.sep, "/")
            pages[rel] = page_name_for(rel)
    return pages


def rewrite_link(target: str, file_rel: str, src: str, pages: dict[str, str], repo: str, ref: str) -> str:
    """Rewrite one link target for the wiki context."""
    if target.startswith(("http://", "https://", "mailto:", "#")):
        return target
    path, sep, anchor = target.partition("#")
    if not path:
        return target  # pure anchor

    is_dir = path.endswith("/")
    # Resolve relative to the source file's location inside the repo.
    file_dir_repo = os.path.dirname(os.path.join(src, file_rel)).replace(os.sep, "/")
    resolved = os.path.normpath(os.path.join(file_dir_repo, path)).replace(os.sep, "/")

    src_prefix = src.replace(os.sep, "/").rstrip("/") + "/"
    if resolved.startswith(src_prefix) and resolved.endswith(".md"):
        inner = resolved[len(src_prefix) :]
        if inner in pages:
            return pages[inner]  # wiki page link; drop code-line anchors
    # Otherwise: a repo file or directory -> absolute GitHub URL.
    kind = "tree" if is_dir else "blob"
    url = f"https://github.com/{repo}/{kind}/{ref}/{resolved}"
    if sep and anchor:
        url += "#" + anchor
    return url


def transform(text: str, file_rel: str, src: str, pages: dict[str, str], repo: str, ref: str) -> str:
    def _sub(m: re.Match) -> str:
        bang, label, target = m.group(1), m.group(2), m.group(3)
        new_target = rewrite_link(target, file_rel, src, pages, repo, ref)
        return f"{bang}[{label}]({new_target})"

    return LINK_RE.sub(_sub, text)


def build_sidebar(pages: dict[str, str]) -> str:
    names = set(pages.values())
    services = sorted(n for n in names if n.startswith("Service-"))
    listed = {n for _, section_names in SIDEBAR_SECTIONS for n in section_names}
    leftovers = sorted(names - listed - set(services))

    lines = ["### AIrport Wiki"]
    for title, section_names in SIDEBAR_SECTIONS:
        entries = [n for n in section_names if n in names]
        if title == "Modules":
            entries += services
        if title == "Internals":
            entries += leftovers
        if not entries:
            continue
        lines += ["", f"**{title}**"]
        lines += [f"- [[{n}]]" for n in entries]
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default="openwiki")
    ap.add_argument("--out", default="wiki")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "Santisoutoo/AIrport"))
    ap.add_argument("--ref", default=os.environ.get("WIKI_BLOB_REF", "main"))
    args = ap.parse_args()

    if not os.path.isdir(args.src):
        print(f"error: source dir not found: {args.src}", file=sys.stderr)
        return 1

    pages = discover_pages(args.src)
    if not pages:
        print(f"error: no .md pages under {args.src}", file=sys.stderr)
        return 1

    os.makedirs(args.out, exist_ok=True)
    written = []
    for rel, page in sorted(pages.items()):
        with open(os.path.join(args.src, rel), encoding="utf-8") as fh:
            content = fh.read()
        new_content = transform(content, rel, args.src, pages, args.repo, args.ref)
        out_path = os.path.join(args.out, f"{page}.md")
        with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new_content)
        written.append((rel, f"{page}.md"))

    with open(os.path.join(args.out, "_Sidebar.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(build_sidebar(pages))

    print(f"Built {len(written)} wiki pages into {args.out}/ (ref={args.ref}):")
    for rel, out in written:
        print(f"  {rel:40s} -> {out}")
    print("  + _Sidebar.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
