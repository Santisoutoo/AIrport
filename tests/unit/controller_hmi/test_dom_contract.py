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

FRONTEND_DIR = (
    Path(__file__).resolve().parents[3]
    / "services"
    / "controller_hmi_service"
    / "frontend"
)

HTML_FILES = [FRONTEND_DIR / "index.html", FRONTEND_DIR / "setup.html"]
JS_DIR = FRONTEND_DIR / "src" / "legacy"

# Ids the JS looks up but creates itself at runtime (never in the HTML).
JS_CREATED_IDS = {
    "smr-svg",            # app.js renderSMRFromData builds the SVG
    "smr-ils-group",      # inside the JS-built SVG
    "smr-aircraft-group",  # inside the JS-built SVG
    "smr-runway-rect",    # inside the JS-built SVG
    "chat-typing",        # ptt.js typing indicator, transient
}

# Id prefixes generated dynamically (per-runway widgets, alerts, screens).
DYNAMIC_ID_PREFIXES = ("xw-", "tw-", "hw-", "rwy-alert-", "screen-")

# Class selectors the JS queries but renders itself at runtime.
JS_CREATED_CLASSES = {
    "flight-strip", "fs-label", "strips-empty",
    "wind-dial", "wind-pair-card", "limit-bar-fill",
    "wind-arrow", "wind-arrow-tip", "wind-gust-arc", "wind-speed-svg",
    "smr-label-bg", "smr-label-line", "smr-label-text",
    "smr-stand", "smr-stand-label", "smr-twy-label-bg", "smr-aircraft-dot",
    "rwy-seq-item", "taf-group", "chat-msg", "chat-bubble",
    "screen",  # static in HTML but also toggled generically
}

# Inline-handler globals -> the module (js during migration, ts after) whose
# public surface must expose them.
MODULE_STEMS = {
    "App": "setup",
    "Asr": "asr",
    "AtisModal": "atis",
    "Ptt": "ptt",
    "Debrief": "debrief",
}


def _read(path: Path) -> str:
    assert path.exists(), f"missing file: {path}"
    return path.read_text(encoding="utf-8")


def _html_sources():
    return {p.name: _read(p) for p in HTML_FILES}


def _js_sources():
    files = sorted(JS_DIR.glob("*.js")) + sorted(JS_DIR.glob("*.ts"))
    assert files, f"no JS/TS files found in {JS_DIR}"
    return {p.name: _read(p) for p in files}


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
    assert not missing, (
        "JS looks up ids that no HTML file defines:\n  " + "\n  ".join(missing)
    )


# ---------------------------------------------------------------------------
# 2. querySelector('#id' / '.class') literals
# ---------------------------------------------------------------------------

def _collect_selector_literals():
    selectors = {}
    pattern = re.compile(
        r"querySelector(?:All)?\(\s*['\"]([#.][A-Za-z0-9_-]+)['\"]\s*\)"
    )
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
            found = re.search(
                rf'class="[^"]*\b{re.escape(token)}\b[^"]*"', html
            ) is not None
        if not found:
            missing.append(f"{selector}  (used by {', '.join(sorted(sources))})")
    assert not missing, (
        "JS queries selectors that no HTML file defines:\n  " + "\n  ".join(missing)
    )


# ---------------------------------------------------------------------------
# 3. Inline on*= handlers -> JS public surface
# ---------------------------------------------------------------------------

def _collect_inline_handlers():
    handlers = {}
    attr_pattern = re.compile(r'\son[a-z]+="([^"]+)"')
    call_pattern = re.compile(r"\b([A-Z][A-Za-z]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*\(")
    for name, src in _html_sources().items():
        for attr in attr_pattern.finditer(src):
            for call in call_pattern.finditer(attr.group(1)):
                handlers.setdefault(call.groups(), set()).add(name)
    return handlers


def test_inline_handlers_exist_in_js_public_surface():
    js = _js_sources()
    handlers = _collect_inline_handlers()
    assert handlers, "no inline handlers found — HTML wiring unexpectedly empty"

    missing = []
    for (module, method), sources in sorted(handlers.items()):
        stem = MODULE_STEMS.get(module)
        js_file = next(
            (name for name in (f"{stem}.ts", f"{stem}.js") if name in js), None
        )
        if stem is None or js_file is None:
            missing.append(
                f"{module}.{method}  (unknown module, used by {', '.join(sorted(sources))})"
            )
            continue
        src = js[js_file]
        defined = re.search(rf"\b{re.escape(method)}\b", src) is not None
        if not defined:
            missing.append(
                f"{module}.{method}  (not found in {js_file}, "
                f"used by {', '.join(sorted(sources))})"
            )
    assert not missing, (
        "HTML inline handlers reference undefined JS functions:\n  "
        + "\n  ".join(missing)
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
        assert (FRONTEND_DIR / ref.lstrip("/")).exists(), (
            f"{html_file.name} references missing script: {ref}"
        )
