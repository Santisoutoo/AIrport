"""Generate the LEST plan with 3 sample taxi routes for the TFG.

Run from the AIrport project root:
    PYTHONPATH=. python scripts/plot_lest_routes.py

Outputs:
    c:/Users/santi/Documents/documentos_tfg/memoria/capitulos/05_resultados/diagramas/lest_rutas.png
"""

from pathlib import Path

import matplotlib.pyplot as plt

from plugins.GND.graph import AirportGraph


OUTPUT = Path(
    r"c:/Users/santi/Documents/documentos_tfg/memoria/"
    r"capitulos/05_resultados/diagramas/lest_rutas.png"
)
GRAPH_JSON = Path("data/airport_data/LEST/LEST_graph.json")


def plot_route(ax, graph, path_node_ids, color, label, linewidth=2.5):
    xs = [graph.nodes[n]["lon"] for n in path_node_ids]
    ys = [graph.nodes[n]["lat"] for n in path_node_ids]
    ax.plot(xs, ys, color=color, linewidth=linewidth, label=label, zorder=3)


def main():
    g = AirportGraph(str(GRAPH_JSON))

    fig, ax = plt.subplots(figsize=(8, 10))

    # Base graph (light grey)
    for u, v in g.graph.edges():
        n1, n2 = g.graph.nodes[u], g.graph.nodes[v]
        ax.plot(
            [n1["lon"], n2["lon"]],
            [n1["lat"], n2["lat"]],
            color="#cccccc",
            linewidth=0.6,
            zorder=1,
        )

    # Stand markers
    for s in g.data.get("stands", []):
        ax.plot(
            s["longitude"],
            s["latitude"],
            "s",
            color="#888888",
            markersize=2.2,
            zorder=2,
        )

    # Runway thresholds
    for rwy_id, (lat, lon) in g._runways_by_id.items():
        ax.plot(lon, lat, "^", color="#1f4e79", markersize=8, zorder=4)
        ax.annotate(
            rwy_id,
            (lon, lat),
            xytext=(6, 6),
            textcoords="offset points",
            fontsize=9,
            color="#1f4e79",
            fontweight="bold",
        )

    # --- Routes ---
    # Route 1: stand 11 area -> runway 35 (direct, no via)
    stand11 = next(s for s in g.data["stands"] if s["stand_id"] == "11")
    r1 = g.find_route_from_position(stand11["latitude"], stand11["longitude"], "35")
    if r1.get("success"):
        plot_route(ax, g.graph, r1["path_node_ids"], "#2e7d32", "Stand 11 -> RWY 35 (directa)")

    # Route 2: stand 11 -> runway 35 forcing via E1 (shows backtracking)
    r2 = g.find_route_from_position(stand11["latitude"], stand11["longitude"], "35", via=["E1"])
    if r2.get("success"):
        plot_route(ax, g.graph, r2["path_node_ids"], "#c62828", "Stand 11 -> RWY 35 via E1", linewidth=1.8)

    # Route 3: free position near stand 19 -> runway 17
    stand19 = next(s for s in g.data["stands"] if s["stand_id"] == "19")
    r3 = g.find_route_from_position(stand19["latitude"], stand19["longitude"], "17")
    if r3.get("success"):
        plot_route(ax, g.graph, r3["path_node_ids"], "#1565c0", "Stand 19 -> RWY 17")

    # Mark route start points
    ax.plot(stand11["longitude"], stand11["latitude"], "o", color="#2e7d32", markersize=8, zorder=5)
    ax.plot(stand19["longitude"], stand19["latitude"], "o", color="#1565c0", markersize=8, zorder=5)

    ax.set_xlabel("Longitud (grados)")
    ax.set_ylabel("Latitud (grados)")
    ax.set_title("Aerodromo de Santiago (LEST): grafo de rodaje y tres rutas de prueba")
    ax.legend(loc="lower right", fontsize=9, framealpha=0.92)
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, linestyle=":", color="#dddddd", linewidth=0.5)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUTPUT, dpi=200, bbox_inches="tight")
    print(f"Saved: {OUTPUT}")
    print(f"Routes: r1={r1.get('success')} r2={r2.get('success')} r3={r3.get('success')}")
    if r1.get("success"):
        print(f"  r1: {len(r1['path_node_ids'])} nodes, {r1['total_distance_m']} m, {r1['taxiway_sequence']}")
    if r2.get("success"):
        print(f"  r2: {len(r2['path_node_ids'])} nodes, {r2['total_distance_m']} m, {r2['taxiway_sequence']}")
    if r3.get("success"):
        print(f"  r3: {len(r3['path_node_ids'])} nodes, {r3['total_distance_m']} m, {r3['taxiway_sequence']}")


if __name__ == "__main__":
    main()
