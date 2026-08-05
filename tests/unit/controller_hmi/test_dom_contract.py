"""DOM-contract regression test for the controller HMI frontend.

The HMI HTML files were once lost because ``*.html`` was gitignored, and the
JS ↔ HTML contract (element ids, class hooks, inline ``on*=`` handlers) only
exists implicitly. This test pins that contract:

1. Every id/class literal the JS looks up must exist in ``index.html`` or
   ``setup.html`` — unless the element is created by JS at runtime
   (explicit allowlist below).
2. Every function referenced from an inline ``on*=`` attribute in the HTML
   must exist in the public surface of the JS module that defines it.
"""

import re
from pathlib import Path

import pytest

FRONTEND_DIR = Path(__file__).resolve().parents[3] / "services" / "controller_hmi_service" / "frontend"

HTML_FILES = [FRONTEND_DIR / "index.html", FRONTEND_DIR / "setup.html"]
SRC_DIR = FRONTEND_DIR / "src"

# Ids the JS looks up but creates itself at runtime (never in the HTML).
JS_CREATED_IDS = {
    "smr-svg",  # app.js renderSMRFromData builds the SVG
    "smr-ils-group",  # inside the JS-built SVG
    "smr-aircraft-group",  # inside the JS-built SVG
    "smr-runway-rect",  # inside the JS-built SVG
    "chat-typing",  # ptt.js typing indicator, transient
}

# Id prefixes generated dynamically (per-runway widgets, alerts, screens).
DYNAMIC_ID_PREFIXES = ("xw-", "tw-", "hw-", "rwy-alert-", "screen-")

# Class selectors the JS queries but renders itself at runtime.
JS_CREATED_CLASSES = {
    "flight-strip",
    "fs-label",
    "strips-empty",
    "wind-dial",
    "wind-pair-card",
    "limit-bar-fill",
    "wind-arrow",
    "wind-arrow-tip",
    "wind-gust-arc",
    "wind-speed-svg",
    "smr-label-bg",
    "smr-label-line",
    "smr-label-text",
    "smr-stand",
    "smr-stand-label",
    "smr-twy-label-bg",
    "smr-aircraft-dot",
    "rwy-seq-item",
    "taf-group",
    "chat-msg",
    "chat-bubble",
    "screen",  # static in HTML but also toggled generically
}


def _read(path: Path) -> str:
    assert path.exists(), f"missing file: {path}"
    return path.read_text(encoding="utf-8")


def _html_sources():
    return {p.name: _read(p) for p in HTML_FILES}


def _js_sources():
    files = sorted(p for p in SRC_DIR.rglob("*.ts") if not p.name.endswith(".test.ts"))
    assert files, f"no TS files found in {SRC_DIR}"
    return {str(p.relative_to(SRC_DIR)): _read(p) for p in files}


def _all_html() -> str:
    return "\n".join(_html_sources().values())


# ---------------------------------------------------------------------------
# 1. getElementById literals
# ---------------------------------------------------------------------------


def _collect_id_literals():
    ids = {}
    pattern = re.compile(r"getElementById\(\s*['\"]([A-Za-z0-9_-]+)['\"]\s*\)")
    for name, src in _js_sources().items():
        for match in pattern.finditer(src):
            ids.setdefault(match.group(1), set()).add(name)
    return ids


def test_every_js_id_lookup_resolves_in_html():
    html = _all_html()
    missing = []
    for element_id, sources in sorted(_collect_id_literals().items()):
        if element_id in JS_CREATED_IDS:
            continue
        if element_id.startswith(DYNAMIC_ID_PREFIXES):
            continue
        if f'id="{element_id}"' not in html:
            missing.append(f"{element_id}  (used by {', '.join(sorted(sources))})")
    assert not missing, "JS looks up ids that no HTML file defines:\n  " + "\n  ".join(missing)


# ---------------------------------------------------------------------------
# 2. querySelector('#id' / '.class') literals
# ---------------------------------------------------------------------------


def _collect_selector_literals():
    selectors = {}
    pattern = re.compile(r"querySelector(?:All)?\(\s*['\"]([#.][A-Za-z0-9_-]+)['\"]\s*\)")
    for name, src in _js_sources().items():
        for match in pattern.finditer(src):
            selectors.setdefault(match.group(1), set()).add(name)
    return selectors


def test_every_js_selector_resolves_in_html():
    html = _all_html()
    missing = []
    for selector, sources in sorted(_collect_selector_literals().items()):
        token = selector[1:]
        if selector.startswith("#"):
            if token in JS_CREATED_IDS or token.startswith(DYNAMIC_ID_PREFIXES):
                continue
            found = f'id="{token}"' in html
        else:
            if token in JS_CREATED_CLASSES:
                continue
            found = re.search(rf'class="[^"]*\b{re.escape(token)}\b[^"]*"', html) is not None
        if not found:
            missing.append(f"{selector}  (used by {', '.join(sorted(sources))})")
    assert not missing, "JS queries selectors that no HTML file defines:\n  " + "\n  ".join(missing)


# ---------------------------------------------------------------------------
# 3. No inline handlers (replaced by addEventListener wiring in Phase 3)
# ---------------------------------------------------------------------------


def test_html_has_no_inline_event_handlers():
    offenders = []
    pattern = re.compile(r'\son[a-z]+="[^"]*"')
    for name, html in _html_sources().items():
        for match in pattern.finditer(html):
            offenders.append(f"{name}: {match.group(0).strip()}")
    assert not offenders, (
        "Inline on*= handlers are forbidden since epic #59 Phase 3 — "
        "wire listeners in the module's init instead:\n  " + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# 4. Script tags reference existing files
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("html_file", HTML_FILES, ids=lambda p: p.name)
def test_script_tags_reference_existing_files(html_file: Path):
    src = _read(html_file)
    for match in re.finditer(r'<script\s+src="([^"]+)"', src):
        ref = match.group(1)
        if ref == "/config.js":
            # Generated by main.py at startup (public/config.js in dev).
            continue
        assert (FRONTEND_DIR / ref.lstrip("/")).exists(), f"{html_file.name} references missing script: {ref}"
