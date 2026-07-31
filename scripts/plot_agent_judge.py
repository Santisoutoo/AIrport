"""Render the LLM-as-judge agent evaluation results as PNG figures.

Reads the CSVs produced by agents_evaluation/judge_responses.py (plus the old
output/agent_benchmark.csv for the latency comparison) and writes paper-ready
figures to docs/benchmark_agents/figs/. Matplotlib only (bundled DejaVu Sans),
same validated palette as scripts/plot_asr_benchmark.py.

Figures:
  chart_judge_pass_rate.png    pass rate per dependency + total
  chart_judge_dimensions.png   per-dimension pass rates per dependency
  chart_judge_latency.png      generation latency: gemini-3-flash-preview vs
                               gemini-3.1-flash-lite (mean + p95)
  chart_judge_phraseology.png  phraseology score distribution (1-5)
  chart_judge_failures.png     dimension involvement across the 93 failures

Usage:
  python scripts/plot_agent_judge.py
"""
import csv
import statistics
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parent.parent
JUDGE = ROOT / "agents_evaluation" / "output"
FIGS = ROOT / "docs" / "benchmark_agents" / "figs"
FIGS.mkdir(parents=True, exist_ok=True)

# ---- palette (light-surface, validated; see plot_asr_benchmark.py) -----------
INK, INK2, MUTED = "#111110", "#52514e", "#898781"
GRID, SURFACE = "#e6e5de", "#ffffff"
DEP_COL = {"DEL": "#2a78d6", "GND": "#1baf7a", "TWR": "#eda100", "TOTAL": "#8a8a86"}
MODEL_BLUES = {"antes": "#184f95", "ahora": "#6da7ec"}   # flash-preview vs 3.1-flash-lite
CRIT = "#c5322f"
DEPS = ["DEL", "GND", "TWR"]

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans"],
    "font.size": 11, "text.color": INK,
    "axes.edgecolor": "#cdccc4", "axes.labelcolor": INK2,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "savefig.dpi": 200, "savefig.bbox": "tight",
})


def style_ax(ax, ymax=None):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    if ymax:
        ax.set_ylim(0, ymax)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


rows = read_csv(JUDGE / "agent_judge_full.csv")
fails = read_csv(JUDGE / "agent_judge_table_failures.csv")


# ---- 1. pass rate per dependency ---------------------------------------------
def fig_pass_rate():
    scopes = DEPS + ["TOTAL"]
    vals, ns = [], []
    for s in scopes:
        sub = rows if s == "TOTAL" else [r for r in rows if r["dep"] == s]
        n_pass = sum(1 for r in sub if r["overall"] == "PASS")
        vals.append(100.0 * n_pass / len(sub))
        ns.append((n_pass, len(sub)))
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    bars = ax.bar(scopes, vals, width=0.62, color=[DEP_COL[s] for s in scopes])
    for b, v, (np_, n) in zip(bars, vals, ns):
        ax.text(b.get_x() + b.get_width() / 2, v + 1.5, f"{v:.0f}%",
                ha="center", fontsize=12, fontweight="bold", color=INK)
        ax.text(b.get_x() + b.get_width() / 2, v - 6, f"{np_}/{n}",
                ha="center", fontsize=9, color="#ffffff")
    style_ax(ax, ymax=100)
    ax.set_ylabel("veredicto PASS del juez (%)")
    ax.set_title("Tasa de aprobado por dependencia — juez gemini-2.5-pro",
                 fontsize=12, loc="left", color=INK)
    fig.savefig(FIGS / "chart_judge_pass_rate.png")
    plt.close(fig)
    print("wrote chart_judge_pass_rate.png")


# ---- 2. per-dimension pass rates ----------------------------------------------
DIMS = [("values_correct", "valores\ncorrectos"),
        ("completeness", "completitud"),
        ("no_hallucination", "sin\nalucinación")]


def _pass_pct(sub, field):
    app = [r for r in sub if r[field] in ("PASS", "FAIL")]
    return 100.0 * sum(1 for r in app if r[field] == "PASS") / len(app) if app else 0.0


def fig_dimensions():
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    width = 0.26
    for di, dep in enumerate(DEPS):
        sub = [r for r in rows if r["dep"] == dep]
        vals = [_pass_pct(sub, f) for f, _ in DIMS]
        xs = [i + (di - 1) * width for i in range(len(DIMS))]
        bars = ax.bar(xs, vals, width=width - 0.03, color=DEP_COL[dep], label=dep)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 1.2, f"{v:.0f}",
                    ha="center", fontsize=9, color=INK)
    ax.set_xticks(range(len(DIMS)), [lbl for _, lbl in DIMS])
    style_ax(ax, ymax=112)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_ylabel("PASS (%) sobre entradas aplicables")
    ax.set_title("Dimensiones de la rúbrica por dependencia",
                 fontsize=12, loc="left", color=INK, pad=30)
    ax.legend(frameon=False, ncols=3, loc="lower right",
              bbox_to_anchor=(1.0, 1.0), borderaxespad=0, fontsize=10)
    fig.savefig(FIGS / "chart_judge_dimensions.png")
    plt.close(fig)
    print("wrote chart_judge_dimensions.png")


# ---- 3. latency: previous model vs current ------------------------------------
def _old_latencies():
    """Per-dep latency lists from the previous benchmark (gemini-3-flash-preview)."""
    path = ROOT / "output" / "agent_benchmark.csv"
    if not path.exists():
        return None
    old = read_csv(path)
    out = {}
    for dep in DEPS:
        lats = [float(r["latency_s"]) for r in old
                if r["dep"] == dep and r["status"] == "200"]
        if lats:
            out[dep] = lats
    return out or None


def fig_latency():
    old = _old_latencies()
    if not old:
        print("skip chart_judge_latency.png (no output/agent_benchmark.csv)")
        return
    new = {dep: [float(r["agent_latency_s"]) for r in rows
                 if r["dep"] == dep and r["status"] == "200"] for dep in DEPS}

    def p95(xs):
        return statistics.quantiles(xs, n=100, method="inclusive")[94]

    fig, axes = plt.subplots(1, 2, figsize=(8.6, 3.6), sharey=True)
    for ax, (title, fn) in zip(axes, [("media", statistics.mean), ("p95", p95)]):
        width = 0.36
        for mi, (label, data) in enumerate([("gemini-3-flash-preview", old),
                                            ("gemini-3.1-flash-lite", new)]):
            key = "antes" if mi == 0 else "ahora"
            xs = [i + (mi - 0.5) * width for i in range(len(DEPS))]
            vals = [fn(data[dep]) for dep in DEPS]
            bars = ax.bar(xs, vals, width=width - 0.04,
                          color=MODEL_BLUES[key], label=label)
            for b, v in zip(bars, vals):
                ax.text(b.get_x() + b.get_width() / 2, v + 0.35, f"{v:.1f}",
                        ha="center", fontsize=9, color=INK)
        ax.set_xticks(range(len(DEPS)), DEPS)
        style_ax(ax)
        ax.set_title(f"latencia {title} (s)", fontsize=11, loc="left", color=INK2)
    axes[0].set_ylabel("segundos")
    axes[0].legend(frameon=False, fontsize=9, loc="upper right")
    fig.suptitle("Tiempo de generación de la respuesta: modelo anterior vs actual",
                 fontsize=12, x=0.125, ha="left", color=INK)
    fig.savefig(FIGS / "chart_judge_latency.png")
    plt.close(fig)
    print("wrote chart_judge_latency.png")


# ---- 4. phraseology score distribution -----------------------------------------
def fig_phraseology():
    counts = Counter(int(r["phraseology_score"]) for r in rows
                     if str(r["phraseology_score"]).isdigit())
    scores = [1, 2, 3, 4, 5]
    vals = [counts.get(s, 0) for s in scores]
    colors = [CRIT if s <= 2 else DEP_COL["DEL"] for s in scores]
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    bars = ax.bar([str(s) for s in scores], vals, width=0.62, color=colors)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 3, str(v),
                ha="center", fontsize=11, fontweight="bold", color=INK)
    style_ax(ax)
    ax.set_xlabel("nota de fraseología del juez (1–5)")
    ax.set_ylabel("entradas")
    ax.set_title("Distribución de la nota de fraseología (300 readbacks)",
                 fontsize=12, loc="left", color=INK)
    ax.legend(handles=[Patch(color=CRIT, label="≤ 2 ⇒ FAIL global"),
                       Patch(color=DEP_COL["DEL"], label="≥ 3")],
              frameon=False, fontsize=9)
    fig.savefig(FIGS / "chart_judge_phraseology.png")
    plt.close(fig)
    print("wrote chart_judge_phraseology.png")


# ---- 5. failure dimension involvement ------------------------------------------
def fig_failures():
    dim_counter: Counter = Counter()
    for f in fails:
        dims = {d.split("(")[0] for d in (f["failed_dimensions"] or "").split(";") if d}
        for d in dims:
            dim_counter[d] += 1
    labels = {"phraseology": "fraseología (≤2)", "completeness": "completitud",
              "no_hallucination": "alucinación", "values_correct": "valores incorrectos"}
    items = dim_counter.most_common()
    names = [labels.get(k, k) for k, _ in items][::-1]
    vals = [v for _, v in items][::-1]
    fig, ax = plt.subplots(figsize=(6.8, 3.2))
    bars = ax.barh(names, vals, height=0.58, color=DEP_COL["DEL"])
    for b, v in zip(bars, vals):
        ax.text(v + 0.8, b.get_y() + b.get_height() / 2,
                f"{v}  ({100 * v / len(fails):.0f}%)",
                va="center", fontsize=10, color=INK)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_xlim(0, max(vals) * 1.22)
    ax.set_xlabel(f"fallos en los que interviene la dimensión (de {len(fails)})")
    ax.set_title("Qué dimensión provoca los fallos", fontsize=12, loc="left", color=INK)
    fig.savefig(FIGS / "chart_judge_failures.png")
    plt.close(fig)
    print("wrote chart_judge_failures.png")


if __name__ == "__main__":
    fig_pass_rate()
    fig_dimensions()
    fig_latency()
    fig_phraseology()
    fig_failures()
    print(f"figs -> {FIGS}")
