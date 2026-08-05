"""Render the ASR benchmark results (tables + charts) as PNG images.

Reads the per-request trace CSVs produced by agents_evaluation/benchmark_asr.py
and writes paper-ready figures to output/asr_bench/figs/. Matplotlib only
(bundled DejaVu Sans, no external fonts). Palette = the validated data-viz
categorical slots (blue / aqua / yellow) for del / gnd / twr.

Multi-config aware: every CSV matching output/asr_bench/asr_<model>_<tier>_<ctx>.csv
is discovered and labelled ("medium c2 fp32", "medium ct2 int8", "medium g1 L4",
"tiny c2"). The original single-config figures (medium/tiny on c2) are still
produced from those specific CSVs; the config-comparison charts render with
whatever configs are present and skip cleanly (with a print) when the data they
need is missing — no crash when only c2 exists today.

Usage:
  python scripts/plot_asr_benchmark.py
"""

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "output" / "asr_bench"
FIGS = BENCH / "figs"
FIGS.mkdir(parents=True, exist_ok=True)

# ---- palette (light-surface, validated) --------------------------------------
INK, INK2, MUTED = "#111110", "#52514e", "#898781"
GRID, SURFACE = "#e6e5de", "#ffffff"
DEP_COL = {"del": "#2a78d6", "gnd": "#1baf7a", "twr": "#eda100", "ALL": "#8a8a86"}
SDI_COL = {"S": "#184f95", "D": "#3987e5", "I": "#9ec5f4"}
# blue ramp for per-configuration series (dark -> light)
CONFIG_BLUES = ["#184f95", "#2a78d6", "#6da7ec", "#9ec5f4"]
CRIT = "#c5322f"
DEPNAME = {"del": "Delivery", "gnd": "Ground", "twr": "Tower", "ALL": "All"}
TIER_EXTRA = {"c2": "fp32", "ct2": "int8", "g1": "L4"}

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans"],
        "font.size": 11,
        "text.color": INK,
        "axes.edgecolor": "#cdccc4",
        "axes.labelcolor": INK2,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
    }
)


# ---- load --------------------------------------------------------------------
def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_csv(path):
    with open(path, encoding="utf-8") as f:
        rd = csv.DictReader(f)
        rows = [r for r in rd if r.get("http_status") == "200"]
        return rows, list(rd.fieldnames or [])


def config_label(model, tier):
    extra = TIER_EXTRA.get(tier)
    if extra and model != "tiny":
        return f"{model} {tier} {extra}"
    return f"{model} {tier}"


def discover_configs():
    out = []
    for p in sorted(BENCH.glob("asr_*_*.csv")):
        rest = p.stem[len("asr_") :]
        parts = rest.rsplit("_", 2)
        if len(parts) != 3:
            continue
        model, tier, ctx = parts
        rows, fields = load_csv(p)
        out.append(
            {
                "model": model,
                "tier": tier,
                "ctx": ctx,
                "rows": rows,
                "fields": fields,
                "label": config_label(model, tier),
                "key": f"{model} {tier} {ctx}",
            }
        )
    return out


CONFIGS = discover_configs()


def get_rows(model, tier, ctx="generic"):
    for c in CONFIGS:
        if c["model"] == model and c["tier"] == tier and c["ctx"] == ctx:
            return c["rows"]
    return []


def median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else 0.0


def agg(rows):
    out = {}
    for scope in ["del", "gnd", "twr", "ALL"]:
        s = [r for r in rows if scope == "ALL" or r["dep"] == scope]
        if not s:
            continue
        S = sum(int(r["sub_raw"]) for r in s)
        D = sum(int(r["del_raw"]) for r in s)
        I = sum(int(r["ins_raw"]) for r in s)
        W = sum(int(r["n_ref"]) for r in s)
        durs = sorted(num(r["duration_s"]) for r in s if num(r["duration_s"]) is not None)
        p50 = durs[len(durs) // 2] if durs else 0.0
        out[scope] = {"n": len(s), "wer": (S + D + I) / W if W else 0.0, "S": S, "D": D, "I": I, "p50": p50}
    return out


# ---- the two reference single-config datasets (medium / tiny on c2 generic) ---
med_rows = get_rows("medium", "c2", "generic")
tin_rows = get_rows("tiny", "c2", "generic")
M = agg(med_rows) if med_rows else {}
T = agg(tin_rows) if tin_rows else {}
PA = (
    [
        {
            "id": r["audio_id"],
            "dep": r["dep"],
            "wer": num(r["wer_raw"]),
            "dur": num(r["duration_s"]),
            "adur": num(r["audio_dur_s"]),
        }
        for r in med_rows
    ]
    if med_rows
    else []
)


def save(fig, name):
    p = FIGS / name
    fig.savefig(p)
    plt.close(fig)
    print("wrote", p.relative_to(ROOT))


# =============================================================================
# 1. Summary table (medium, per position)
# =============================================================================
def table_summary():
    if not M:
        print("[skip] table_summary: no medium c2 generic CSV")
        return
    fig, ax = plt.subplots(figsize=(7.6, 2.5))
    ax.axis("off")
    cols = ["Position", "n", "WER", "Sub", "Del", "Ins", "Server p50"]
    rows, colors = [], []
    for d in ["del", "gnd", "twr", "ALL"]:
        a = M[d]
        rows.append([DEPNAME[d], a["n"], f"{a['wer'] * 100:.1f}%", a["S"], a["D"], a["I"], f"{a['p50']:.0f} s"])
        colors.append(DEP_COL[d])
    tbl = ax.table(cellText=rows, colLabels=cols, cellLoc="center", loc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(11)
    tbl.scale(1, 1.7)
    for (r, c), cell in tbl.get_celld().items():
        cell.set_edgecolor("#e6e5de")
        if r == 0:
            cell.set_facecolor("#f4f4f0")
            cell.set_text_props(color=INK2, fontweight="bold")
        else:
            if c == 0:
                cell.set_text_props(color=colors[r - 1], fontweight="bold", ha="left")
                cell.PAD = 0.04
            if rows[r - 1][0] == "All":
                cell.set_facecolor("#faf9f6")
                cell.set_text_props(fontweight="bold")
    ax.set_title(
        "Medium — word error rate by controller position", fontsize=13, fontweight="bold", color=INK, loc="left", pad=14
    )
    fig.text(
        0.5,
        0.02,
        "60 synthesized clips · raw transcription vs reference · CPU 2 vCPU",
        ha="center",
        color=MUTED,
        fontsize=9,
    )
    save(fig, "table_summary_medium.png")


# =============================================================================
# 2. Model comparison table (tiny vs medium)
# =============================================================================
def table_compare():
    if not M or not T:
        print("[skip] table_compare: needs medium + tiny c2 generic CSVs")
        return
    fig, ax = plt.subplots(figsize=(9.6, 1.9))
    ax.axis("off")
    cols = ["Model", "Params", "WER (all)", "Subs", "Del", "Ins", "Verdict"]
    rows = [
        [
            "tiny",
            "~38 M",
            f"{T['ALL']['wer'] * 100:.0f}%",
            T["ALL"]["S"],
            T["ALL"]["D"],
            T["ALL"]["I"],
            "Unusable (loops)",
        ],
        ["medium", "~770 M", f"{M['ALL']['wer'] * 100:.1f}%", M["ALL"]["S"], M["ALL"]["D"], M["ALL"]["I"], "Usable"],
    ]
    tbl = ax.table(
        cellText=rows,
        colLabels=cols,
        cellLoc="center",
        loc="center",
        colWidths=[0.12, 0.12, 0.14, 0.11, 0.09, 0.11, 0.24],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(11)
    tbl.scale(1, 1.9)
    for (r, c), cell in tbl.get_celld().items():
        cell.set_edgecolor("#e6e5de")
        if r == 0:
            cell.set_facecolor("#f4f4f0")
            cell.set_text_props(color=INK2, fontweight="bold")
        elif c == 6:
            cell.set_text_props(color=CRIT if r == 1 else "#0a8a0a", fontweight="bold")
        elif c == 2:
            cell.set_text_props(color=CRIT if r == 1 else "#0a8a0a", fontweight="bold")
    ax.set_title(
        "tiny vs medium (jlvdoorn atco2) — same 60 audios",
        fontsize=13,
        fontweight="bold",
        color=INK,
        loc="left",
        pad=14,
    )
    save(fig, "table_model_comparison.png")


# =============================================================================
# 3. WER by position (horizontal bars)
# =============================================================================
def chart_wer():
    if not M:
        print("[skip] chart_wer: no medium c2 generic CSV")
        return
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    order = ["del", "gnd", "twr", "ALL"]
    ys = range(len(order))
    vals = [M[d]["wer"] * 100 for d in order]
    cols = [DEP_COL[d] for d in order]
    bars = ax.barh(ys, vals, color=cols, height=0.62, zorder=3)
    bars[-1].set_alpha(0.55)
    for y, v in zip(ys, vals):
        ax.text(v + 0.3, y, f"{v:.1f}%", va="center", ha="left", fontsize=11, fontweight="bold", color=INK)
    ax.set_yticks(list(ys))
    ax.set_yticklabels([DEPNAME[d] for d in order], fontweight="bold")
    ax.invert_yaxis()
    ax.set_xlim(0, 16)
    ax.set_xlabel("Word error rate (%)")
    ax.xaxis.grid(True, color=GRID, zorder=0)
    ax.set_axisbelow(True)
    for s in ["top", "right", "left"]:
        ax.spines[s].set_visible(False)
    ax.set_title("Medium — WER by controller position", fontsize=13, fontweight="bold", color=INK, loc="left", pad=10)
    save(fig, "chart_wer_by_position.png")


# =============================================================================
# 4. Error composition S/D/I (stacked)
# =============================================================================
def chart_sdi():
    if not M:
        print("[skip] chart_sdi: no medium c2 generic CSV")
        return
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    order = ["del", "gnd", "twr", "ALL"]
    ys = range(len(order))
    left = [0] * len(order)
    for key in ["S", "D", "I"]:
        vals = [M[d][key] for d in order]
        ax.barh(
            ys,
            vals,
            left=left,
            color=SDI_COL[key],
            height=0.62,
            edgecolor="white",
            linewidth=1.2,
            zorder=3,
            label={"S": "Substitutions", "D": "Deletions", "I": "Insertions"}[key],
        )
        left = [l + v for l, v in zip(left, vals)]
    for y, tot in zip(ys, left):
        ax.text(tot + 1, y, str(tot), va="center", ha="left", fontsize=10, color=INK2)
    ax.set_yticks(list(ys))
    ax.set_yticklabels([DEPNAME[d] for d in order], fontweight="bold")
    ax.invert_yaxis()
    ax.set_xlim(0, 120)
    ax.set_xlabel("Word errors (count)")
    ax.xaxis.grid(True, color=GRID, zorder=0)
    ax.set_axisbelow(True)
    for s in ["top", "right", "left"]:
        ax.spines[s].set_visible(False)
    ax.legend(loc="upper right", frameon=False, fontsize=9.5)
    ax.set_title(
        "Medium — where the errors come from (S / D / I)", fontsize=13, fontweight="bold", color=INK, loc="left", pad=10
    )
    save(fig, "chart_error_composition.png")


# =============================================================================
# 5. Per-utterance WER, sorted
# =============================================================================
def chart_dist():
    if not PA:
        print("[skip] chart_dist: no medium c2 generic CSV")
        return
    fig, ax = plt.subplots(figsize=(9.6, 3.2))
    data = sorted(PA, key=lambda p: p["wer"])
    xs = range(len(data))
    vals = [p["wer"] * 100 for p in data]
    # zero-WER clips (mostly Tower) get a visible 0.7% stub so "perfect" still reads
    disp = [max(v, 0.7) for v in vals]
    cols = [DEP_COL[p["dep"]] for p in data]
    ax.bar(xs, disp, color=cols, width=0.82, zorder=3)
    ax.set_xlim(-1, len(data))
    ax.set_ylim(0, 55)
    ax.set_ylabel("Word error rate (%)")
    ax.set_xticks([])
    ax.yaxis.grid(True, color=GRID, zorder=0)
    ax.set_axisbelow(True)
    for s in ["top", "right", "bottom"]:
        ax.spines[s].set_visible(False)
    n_perfect = sum(1 for v in vals if v == 0)
    ax.text(0, -4, "best", color=MUTED, fontsize=9)
    ax.text(len(data) - 1, -4, "worst", color=MUTED, fontsize=9, ha="right")
    ax.text(
        (n_perfect - 1) / 2, 3.6, f"{n_perfect} perfect (0%)", color=MUTED, fontsize=8.5, ha="center", style="italic"
    )
    worst = data[-1]
    ax.annotate(
        f"{worst['id']}  {worst['wer'] * 100:.0f}%",
        xy=(len(data) - 1, worst["wer"] * 100),
        xytext=(len(data) - 4, 45),
        ha="right",
        fontsize=9,
        color=INK2,
        arrowprops=dict(arrowstyle="->", color=MUTED, lw=1),
    )
    ax.legend(
        handles=[Patch(color=DEP_COL[d], label=DEPNAME[d]) for d in ["del", "gnd", "twr"]],
        loc="upper left",
        frameon=False,
        fontsize=9.5,
    )
    ax.set_title(
        "Medium — every utterance, sorted best to worst (60 audios)",
        fontsize=13,
        fontweight="bold",
        color=INK,
        loc="left",
        pad=10,
    )
    save(fig, "chart_wer_distribution.png")


# =============================================================================
# 6. Inference time vs audio length (RTF)
# =============================================================================
def chart_rtf():
    if not PA:
        print("[skip] chart_rtf: no medium c2 generic CSV")
        return
    fig, ax = plt.subplots(figsize=(8.4, 3.6))
    for d in ["del", "gnd", "twr"]:
        pts = [p for p in PA if p["dep"] == d]
        ax.scatter(
            [p["adur"] for p in pts],
            [p["dur"] for p in pts],
            s=44,
            color=DEP_COL[d],
            edgecolor="white",
            linewidth=0.8,
            alpha=0.9,
            zorder=3,
            label=DEPNAME[d],
        )
    for r, lab, lx, ly in [(10, "10×", 9.0, 93), (5, "5×", 15.2, 74)]:
        xe = min(16, 100 / r)
        ax.plot([0, xe], [0, r * xe], "--", color="#cdccc4", lw=1, zorder=1)
        ax.text(lx, ly, lab, color=MUTED, fontsize=9, ha="right", va="bottom", style="italic")
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 100)
    ax.set_xlabel("Audio length (s)")
    ax.set_ylabel("Server inference time (s)")
    ax.grid(True, color=GRID, zorder=0)
    ax.set_axisbelow(True)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    ax.legend(loc="lower right", frameon=False, fontsize=9.5)
    ax.set_title(
        "Medium on CPU — inference time vs clip length (RTF ≈ 9×)",
        fontsize=13,
        fontweight="bold",
        color=INK,
        loc="left",
        pad=10,
    )
    save(fig, "chart_rtf_scatter.png")


# =============================================================================
# 7. Processing time per audio (medium, sorted)
# =============================================================================
def chart_proc_time():
    if not PA:
        print("[skip] chart_proc_time: no medium c2 generic CSV")
        return
    fig, ax = plt.subplots(figsize=(9.6, 3.2))
    data = sorted(PA, key=lambda p: p["dur"])
    xs = range(len(data))
    vals = [p["dur"] for p in data]
    cols = [DEP_COL[p["dep"]] for p in data]
    top = max(vals) * 1.14
    ax.bar(xs, vals, color=cols, width=0.82, zorder=3)
    med = sorted(vals)[len(vals) // 2]
    ax.axhline(med, color=INK2, lw=1.3, ls="--", zorder=4)
    ax.text(
        len(data) - 1,
        med + 1.5,
        f"median {med:.0f} s",
        color=INK2,
        fontsize=9.5,
        va="bottom",
        ha="right",
        fontweight="bold",
    )
    ax.set_xlim(-1, len(data))
    ax.set_ylim(0, top)
    ax.set_ylabel("Server processing time (s)")
    ax.set_xticks([])
    ax.yaxis.grid(True, color=GRID, zorder=0)
    ax.set_axisbelow(True)
    for s in ["top", "right", "bottom"]:
        ax.spines[s].set_visible(False)
    ax.text(0, -top * 0.08, "fastest", color=MUTED, fontsize=9)
    ax.text(len(data) - 1, -top * 0.08, "slowest", color=MUTED, fontsize=9, ha="right")
    ax.legend(
        handles=[Patch(color=DEP_COL[d], label=DEPNAME[d]) for d in ["del", "gnd", "twr"]],
        loc="upper left",
        frameon=False,
        fontsize=9.5,
    )
    ax.set_title(
        "Medium on CPU — processing time per audio (60 clips, sorted)",
        fontsize=13,
        fontweight="bold",
        color=INK,
        loc="left",
        pad=10,
    )
    save(fig, "chart_processing_time.png")


# =============================================================================
# 8. Processing time — tiny vs medium (box + points)
# =============================================================================
def chart_proc_compare():
    if not PA or not tin_rows:
        print("[skip] chart_proc_compare: needs medium + tiny c2 generic CSVs")
        return
    fig, ax = plt.subplots(figsize=(8.0, 3.4))
    tin_pa = [{"dep": r["dep"], "dur": num(r["duration_s"])} for r in tin_rows if num(r["duration_s"]) is not None]
    series = [("tiny", tin_pa, "~38 M"), ("medium", PA, "~770 M")]
    import random

    random.seed(1)
    for i, (name, pa, _) in enumerate(series):
        durs = [p["dur"] for p in pa]
        bp = ax.boxplot(
            [durs],
            positions=[i],
            widths=0.5,
            vert=True,
            patch_artist=True,
            showfliers=False,
            zorder=2,
            medianprops=dict(color=INK, lw=1.6),
            boxprops=dict(facecolor="#f4f4f0", edgecolor="#cdccc4"),
            whiskerprops=dict(color="#cdccc4"),
            capprops=dict(color="#cdccc4"),
        )
        for p in pa:
            ax.scatter(
                i + (random.random() - 0.5) * 0.34,
                p["dur"],
                s=26,
                color=DEP_COL[p["dep"]],
                edgecolor="white",
                linewidth=0.6,
                alpha=0.85,
                zorder=3,
            )
        med = sorted(durs)[len(durs) // 2]
        ax.text(i, med, f"  {med:.0f} s", va="center", ha="left", fontsize=10, fontweight="bold", color=INK)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["tiny\n~38 M", "medium\n~770 M"], fontweight="bold")
    ax.set_ylim(0, 100)
    ax.set_ylabel("Server processing time (s)")
    ax.yaxis.grid(True, color=GRID, zorder=0)
    ax.set_axisbelow(True)
    for s in ["top", "right", "bottom"]:
        ax.spines[s].set_visible(False)
    ax.legend(
        handles=[Patch(color=DEP_COL[d], label=DEPNAME[d]) for d in ["del", "gnd", "twr"]],
        loc="upper left",
        frameon=False,
        fontsize=9,
    )
    ax.text(
        0.5,
        0.34,
        "tiny ~3× faster —\nbut loops (unusable)",
        transform=ax.transAxes,
        color=MUTED,
        fontsize=9.5,
        va="center",
        ha="center",
        style="italic",
    )
    ax.set_title(
        "Processing time per audio — tiny vs medium (2 vCPU)",
        fontsize=13,
        fontweight="bold",
        color=INK,
        loc="left",
        pad=10,
    )
    save(fig, "chart_processing_time_compare.png")


# =============================================================================
# 9. Latency by configuration (box + points, all tiers)  [NEW]
# =============================================================================
def chart_latency_by_config():
    # One box per (model, tier); if several contexts exist for the same compute
    # tier, keep one (latency is a property of the tier, not the prompt).
    order_ctx = {"generic": 0, "none": 1, "session": 2}
    seen = {}
    for c in CONFIGS:
        durs = [num(r["duration_s"]) for r in c["rows"] if num(r["duration_s"]) is not None]
        if not durs:
            continue
        k = (c["model"], c["tier"])
        if k not in seen or order_ctx.get(c["ctx"], 9) < order_ctx.get(seen[k]["ctx"], 9):
            seen[k] = c
    items = list(seen.values())
    if not items:
        print("[skip] chart_latency_by_config: no configs with duration data")
        return
    items.sort(key=lambda c: -median([num(r["duration_s"]) for r in c["rows"] if num(r["duration_s"]) is not None]))
    import random

    random.seed(3)
    fig, ax = plt.subplots(figsize=(max(6.4, 1.9 * len(items) + 2.0), 3.6))
    for i, c in enumerate(items):
        durs = [num(r["duration_s"]) for r in c["rows"] if num(r["duration_s"]) is not None]
        blue = CONFIG_BLUES[i % len(CONFIG_BLUES)]
        ax.boxplot(
            [durs],
            positions=[i],
            widths=0.5,
            vert=True,
            patch_artist=True,
            showfliers=False,
            zorder=2,
            medianprops=dict(color=INK, lw=1.6),
            boxprops=dict(facecolor="#f4f4f0", edgecolor=blue),
            whiskerprops=dict(color=blue),
            capprops=dict(color=blue),
        )
        for r in c["rows"]:
            d = num(r["duration_s"])
            if d is None:
                continue
            ax.scatter(
                i + (random.random() - 0.5) * 0.34,
                d,
                s=24,
                color=DEP_COL.get(r["dep"], "#8a8a86"),
                edgecolor="white",
                linewidth=0.6,
                alpha=0.85,
                zorder=3,
            )
        med = median(durs)
        ax.text(i, med, f"  {med:.0f} s", va="center", ha="left", fontsize=10, fontweight="bold", color=INK)
    ax.set_xticks(range(len(items)))
    ax.set_xticklabels([c["label"] for c in items], fontweight="bold")
    ax.set_ylabel("Server processing time (s)")
    ax.set_ylim(0, None)
    ax.yaxis.grid(True, color=GRID, zorder=0)
    ax.set_axisbelow(True)
    for s in ["top", "right", "bottom"]:
        ax.spines[s].set_visible(False)
    ax.legend(
        handles=[Patch(color=DEP_COL[d], label=DEPNAME[d]) for d in ["del", "gnd", "twr"]],
        loc="upper right",
        frameon=False,
        fontsize=9,
    )
    ax.set_title(
        "Latency by configuration — server processing time per audio",
        fontsize=13,
        fontweight="bold",
        color=INK,
        loc="left",
        pad=10,
    )
    save(fig, "chart_latency_by_config.png")


# =============================================================================
# 10. WER by config × context — raw vs post  [NEW]
# =============================================================================
def chart_wer_context():
    groups = []
    for c in CONFIGS:
        raws = [num(r["wer_raw"]) for r in c["rows"] if num(r["wer_raw"]) is not None]
        if not raws:
            continue
        mraw = sum(raws) / len(raws)
        if mraw > 1.5:  # looping / unusable model would flatten the scale
            continue
        posts = [num(r["wer_post"]) for r in c["rows"] if num(r["wer_post"]) is not None]
        mpost = sum(posts) / len(posts) if posts else 0.0
        groups.append((c, mraw * 100, mpost * 100))
    if not groups:
        print("[skip] chart_wer_context: no usable configs (wer_raw)")
        return
    fig, ax = plt.subplots(figsize=(max(6.0, 1.8 * len(groups) + 2.0), 3.4))
    xs = range(len(groups))
    bw = 0.38
    b1 = ax.bar([x - bw / 2 for x in xs], [g[1] for g in groups], bw, color="#2a78d6", zorder=3, label="WER raw")
    b2 = ax.bar([x + bw / 2 for x in xs], [g[2] for g in groups], bw, color="#9ec5f4", zorder=3, label="WER post")
    for bars in (b1, b2):
        for b in bars:
            ax.text(
                b.get_x() + b.get_width() / 2,
                b.get_height() + 0.25,
                f"{b.get_height():.1f}",
                ha="center",
                va="bottom",
                fontsize=9,
                color=INK2,
            )
    ax.set_xticks(list(xs))
    ax.set_xticklabels([f"{g[0]['label']}\n{g[0]['ctx']}" for g in groups], fontweight="bold")
    ax.set_ylabel("Word error rate (%)")
    ax.yaxis.grid(True, color=GRID, zorder=0)
    ax.set_axisbelow(True)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    ax.legend(loc="upper right", frameon=False, fontsize=9.5)
    ax.set_title(
        "WER by configuration and context — raw vs post-processed",
        fontsize=13,
        fontweight="bold",
        color=INK,
        loc="left",
        pad=10,
    )
    save(fig, "chart_wer_context.png")


# =============================================================================
# 11. Entity recovery — callsign / SID accuracy  [NEW]
# =============================================================================
def _entity_pct(rows, correct_col, canon_col):
    sub = [r for r in rows if r.get(canon_col, "")]
    if not sub:
        return None
    return 100.0 * sum(1 for r in sub if str(r.get(correct_col, "")).lower() == "true") / len(sub)


def chart_entity_accuracy():
    groups = [c for c in CONFIGS if "cs_correct" in (c["fields"] or [])]
    if not groups:
        print("[skip] chart_entity_accuracy: no CSV has entity columns yet")
        return
    data = []
    for c in groups:
        cs = _entity_pct(c["rows"], "cs_correct", "cs_canonical")
        sid = _entity_pct(c["rows"], "sid_correct", "sid_canonical")
        data.append((c, cs or 0.0, sid or 0.0))
    fig, ax = plt.subplots(figsize=(max(6.0, 1.8 * len(data) + 2.0), 3.4))
    xs = range(len(data))
    bw = 0.38
    b1 = ax.bar([x - bw / 2 for x in xs], [d[1] for d in data], bw, color="#184f95", zorder=3, label="Callsign")
    b2 = ax.bar([x + bw / 2 for x in xs], [d[2] for d in data], bw, color="#6da7ec", zorder=3, label="SID")
    for bars in (b1, b2):
        for b in bars:
            ax.text(
                b.get_x() + b.get_width() / 2,
                b.get_height() + 1.0,
                f"{b.get_height():.0f}%",
                ha="center",
                va="bottom",
                fontsize=9,
                color=INK2,
            )
    ax.set_xticks(list(xs))
    ax.set_xticklabels([f"{d[0]['label']}\n{d[0]['ctx']}" for d in data], fontweight="bold")
    ax.set_ylabel("Entity recovered (%)")
    ax.set_ylim(0, 108)
    ax.yaxis.grid(True, color=GRID, zorder=0)
    ax.set_axisbelow(True)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    ax.legend(loc="upper right", frameon=False, fontsize=9.5)
    ax.set_title(
        "Entity recovery — callsign & SID accuracy by configuration",
        fontsize=13,
        fontweight="bold",
        color=INK,
        loc="left",
        pad=10,
    )
    save(fig, "chart_entity_accuracy.png")


if __name__ == "__main__":
    labels = ", ".join(c["key"] for c in CONFIGS) or "(none)"
    print(f"discovered configs: {labels}\n")
    table_summary()
    table_compare()
    chart_wer()
    chart_sdi()
    chart_dist()
    chart_rtf()
    chart_proc_time()
    chart_proc_compare()
    chart_latency_by_config()
    chart_wer_context()
    chart_entity_accuracy()
    print("\nAll figures ->", FIGS.relative_to(ROOT))
