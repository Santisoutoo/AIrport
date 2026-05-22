"""Plot a clean view of the LEST taxi graph for memoria 5.3.1.

No taxi routes — just the underlying graph: edges, nodes (highlighting the
main connected component), stands and runway thresholds. Companion to the
metrics table tab:rutas-metricas.
"""
from pathlib import Path

import matplotlib.pyplot as plt

from plugins.GND.graph import AirportGraph


OUT = Path(
    r"c:/Users/santi/Documents/documentos_tfg/memoria/"
    r"capitulos/05_resultados/diagramas/lest_grafo.png"
)
GRAPH_JSON = Path("data/airport_data/LEST/LEST_graph.json")


def main():
    g = AirportGraph(str(GRAPH_JSON))

    fig, ax = plt.subplots(figsize=(5.5, 7))

    # Edges
    for u, v in g.graph.edges():
        n1, n2 = g.graph.nodes[u], g.graph.nodes[v]
        ax.plot(
            [n1["lon"], n2["lon"]], [n1["lat"], n2["lat"]],
            color="#9aa6b2", linewidth=0.8, zorder=1,
        )

    # All nodes — orphans in light grey, main CC in stronger blue
    main_cc = g._main_cc
    for nid in g.graph.nodes():
        n = g.graph.nodes[nid]
        if nid in main_cc:
            ax.plot(n["lon"], n["lat"], "o", color="#1565c0",
                    markersize=2.5, zorder=2)
        else:
            ax.plot(n["lon"], n["lat"], "o", color="#bfc8d2",
                    markersize=2.0, zorder=2)

    # Stands
    for s in g.data.get("stands", []):
        ax.plot(s["longitude"], s["latitude"],
                "s", color="#666666", markersize=2.5, zorder=3)

    # Runway thresholds
    for rwy_id, (lat, lon) in g._runways_by_id.items():
        ax.plot(lon, lat, "^", color="#0d3b66", markersize=10, zorder=4)
        ax.annotate(rwy_id, (lon, lat), xytext=(7, 7),
                    textcoords="offset points",
                    fontsize=10, color="#0d3b66", fontweight="bold")

    # Legend with proxies
    from matplotlib.lines import Line2D
    legend_items = [
        Line2D([0], [0], marker="^", color="w",
               markerfacecolor="#0d3b66", markersize=9, label="Umbral de pista"),
        Line2D([0], [0], marker="o", color="w",
               markerfacecolor="#1565c0", markersize=7,
               label="Nodo del componente principal"),
        Line2D([0], [0], marker="o", color="w",
               markerfacecolor="#bfc8d2", markersize=7,
               label="Nodo huerfano"),
        Line2D([0], [0], marker="s", color="w",
               markerfacecolor="#666666", markersize=7, label="Estacionamiento"),
        Line2D([0], [0], color="#9aa6b2", linewidth=1.5, label="Arista de rodaje"),
    ]
    ax.legend(handles=legend_items, loc="lower left",
              fontsize=8, framealpha=0.92)

    from matplotlib.ticker import MaxNLocator, FormatStrFormatter
    ax.set_xlabel("Longitud (grados)")
    ax.set_ylabel("Latitud (grados)")
    ax.set_title("Grafo de rodaje de LEST")
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, linestyle=":", color="#dddddd", linewidth=0.5)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
    ax.xaxis.set_major_formatter(FormatStrFormatter("%.3f"))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
    ax.yaxis.set_major_formatter(FormatStrFormatter("%.3f"))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUT}")
    print(f"Stats: {g.graph.number_of_nodes()} nodes, "
          f"{g.graph.number_of_edges()} edges, "
          f"main_cc={len(main_cc)}")


if __name__ == "__main__":
    main()
