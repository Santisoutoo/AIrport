"""Plot a two-panel bar chart summarising the agent benchmark.

Left panel:  conformity per agent (% schema valid + % structured block complete)
Right panel: response latency per agent (p50 + p95 in seconds)

Used by memoria 5.2.2 as a visual companion to Table 5.2 (tab:res-agentes).
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


OUT = Path(
    r"c:/Users/santi/Documents/documentos_tfg/memoria/"
    r"capitulos/05_resultados/diagramas/agent_benchmark.png"
)

# Values come from output/agent_benchmark.csv aggregated summary.
AGENTS = ["DEL", "GND", "TWR"]
PCT_SCHEMA = [100.0, 100.0, 100.0]
PCT_COMPLETE = [100.0, 100.0, 100.0]
P50 = [3.1, 4.5, 2.9]
P95 = [11.4, 17.7, 8.8]

COL_SCHEMA = "#2e7d32"  # green
COL_COMPLETE = "#1565c0"  # blue
COL_P50 = "#ef6c00"  # orange
COL_P95 = "#c62828"  # red


def main():
    fig, (ax_pct, ax_lat) = plt.subplots(1, 2, figsize=(11, 4.2))

    # ---- Left panel: percentages ----
    x = np.arange(len(AGENTS))
    w = 0.35
    b1 = ax_pct.bar(x - w / 2, PCT_SCHEMA, w, color=COL_SCHEMA, label="% schema valido")
    b2 = ax_pct.bar(x + w / 2, PCT_COMPLETE, w, color=COL_COMPLETE, label="% bloque completo")
    ax_pct.set_xticks(x)
    ax_pct.set_xticklabels(AGENTS)
    ax_pct.set_ylim(0, 110)
    ax_pct.set_ylabel("Porcentaje (%)")
    ax_pct.set_title("Conformidad por agente")
    ax_pct.grid(axis="y", linestyle=":", color="#dddddd", linewidth=0.6)
    ax_pct.set_axisbelow(True)
    for bars in (b1, b2):
        for bar in bars:
            h = bar.get_height()
            ax_pct.annotate(
                f"{h:.1f}",
                xy=(bar.get_x() + bar.get_width() / 2, h),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                fontsize=8,
            )
    ax_pct.legend(loc="lower right", fontsize=9, framealpha=0.95)

    # ---- Right panel: latency ----
    b3 = ax_lat.bar(x - w / 2, P50, w, color=COL_P50, label="p50")
    b4 = ax_lat.bar(x + w / 2, P95, w, color=COL_P95, label="p95")
    ax_lat.set_xticks(x)
    ax_lat.set_xticklabels(AGENTS)
    ax_lat.set_ylabel("Latencia (s)")
    ax_lat.set_title("Latencia de respuesta por agente")
    ax_lat.grid(axis="y", linestyle=":", color="#dddddd", linewidth=0.6)
    ax_lat.set_axisbelow(True)
    for bars in (b3, b4):
        for bar in bars:
            h = bar.get_height()
            ax_lat.annotate(
                f"{h:.1f}",
                xy=(bar.get_x() + bar.get_width() / 2, h),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                fontsize=8,
            )
    ax_lat.legend(loc="upper right", fontsize=9, framealpha=0.95)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUT}")


if __name__ == "__main__":
    main()
