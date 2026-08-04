"""Generate airport plans with sample taxi routes for the TFG.

Usage (from the AIrport project root):
    ./.venv/Scripts/python.exe scripts/plot_airport_routes.py LEST
    ./.venv/Scripts/python.exe scripts/plot_airport_routes.py LEIB
    ./.venv/Scripts/python.exe scripts/plot_airport_routes.py LEST --strict

With --strict, routes that carry a via sequence are computed with
find_route_strict_from_position (issue #67) instead of the lenient
find_route_from_position, for visual validation of strict adherence
to the controller sequence. Routes without vias keep the lenient path.

Outputs the PNG into the chapter-5 figure directory of the thesis.
"""
import sys
from pathlib import Path

import matplotlib.pyplot as plt

from plugins.GND.graph import AirportGraph


FIG_DIR = Path(
    r"c:/Users/santi/Documents/documentos_tfg/memoria/"
    r"capitulos/05_resultados/diagramas"
)
DATA_DIR = Path("data/airport_data")


# Per-airport route plan: list of (label, color, start_lat_lon_or_token, end_token, via)
ROUTES = {
    "LEST": [
        # Use stand 11 and stand 19 coordinates from LEST_graph.json.
        # The strict via sequences are realistic controller clearances: the
        # aircraft joins the first named taxiway perpendicularly (straight
        # centerline join) and never leaves the authorized sequence.
        ("Stand 11 -> RWY 35 (directa)",  "#2e7d32", (42.89347487, -8.41920889), "35", None),
        ("Stand 11 -> RWY 35 via D3 R",   "#c62828", (42.89347487, -8.41920889), "35", ["D3", "R"]),
        ("Stand 19 -> RWY 17 via T",      "#1565c0", (42.89546741, -8.41854799), "17", ["T"]),
    ],
    "LEIB": [
        # Stand 07 (north gate) and stand 19A (middle gate) toward RWY 06,
        # plus stand 30 toward the RWY 24 side (using node 164 because the
        # token "24" collides with disconnected node_id 24 in resolve_point).
        ("Stand 07 -> RWY 06", "#2e7d32", (38.876404, 1.374426), "06", None),
        ("Stand 19A -> RWY 06", "#1565c0", (38.873310, 1.367450), "06", None),
        ("Stand 30 -> cerca RWY 24", "#c62828", (38.876600, 1.371450), "164", None),
    ],
}


def plot_route(ax, graph, route, color, label, linewidth=2.2):
    # Prefer waypoints (they include the synthetic centerline-join point,
    # which is what the aircraft actually flies); fall back to graph nodes.
    wps = route.get("waypoints")
    if wps:
        xs = [w["lon"] for w in wps]
        ys = [w["lat"] for w in wps]
    else:
        xs = [graph.nodes[n]["lon"] for n in route["path_node_ids"]]
        ys = [graph.nodes[n]["lat"] for n in route["path_node_ids"]]
    ax.plot(xs, ys, color=color, linewidth=linewidth, label=label, zorder=3)


def plot_airport(icao: str, strict: bool = False):
    json_path = DATA_DIR / icao / f"{icao}_graph.json"
    g = AirportGraph(str(json_path))

    fig, ax = plt.subplots(figsize=(8, 10))

    # Base graph
    for u, v in g.graph.edges():
        n1, n2 = g.graph.nodes[u], g.graph.nodes[v]
        ax.plot(
            [n1["lon"], n2["lon"]], [n1["lat"], n2["lat"]],
            color="#cccccc", linewidth=0.5, zorder=1,
        )

    # Stands
    for s in g.data.get("stands", []):
        ax.plot(
            s["longitude"], s["latitude"],
            "s", color="#888888", markersize=2.0, zorder=2,
        )

    # Runway thresholds
    for rwy_id, (lat, lon) in g._runways_by_id.items():
        ax.plot(lon, lat, "^", color="#1f4e79", markersize=8, zorder=4)
        ax.annotate(
            rwy_id, (lon, lat),
            xytext=(6, 6), textcoords="offset points",
            fontsize=9, color="#1f4e79", fontweight="bold",
        )

    # Routes
    results = []
    for label, color, start, end_token, via in ROUTES[icao]:
        if strict and via:
            label = f"{label} [strict]"
            if isinstance(start, tuple):
                r = g.find_route_strict_from_position(
                    start[0], start[1], via, end_token,
                )
            else:
                r = g.find_route_strict(start, via, end_token)
        elif isinstance(start, tuple):
            r = g.find_route_from_position(start[0], start[1], end_token, via=via)
        else:
            r = g.find_route_via(start, end_token, via=via)
        results.append((label, r))
        if r.get("success"):
            plot_route(ax, g.graph, r, color, label)
            # Start marker + straight join segment to the first waypoint
            # (for strict routes this is the perpendicular centerline join).
            if isinstance(start, tuple):
                ax.plot(start[1], start[0], "o", color=color, markersize=7, zorder=5)
                wps = r.get("waypoints")
                if wps:
                    ax.plot(
                        [start[1], wps[0]["lon"]], [start[0], wps[0]["lat"]],
                        color=color, linewidth=1.4, linestyle="--", zorder=3,
                    )

    ax.set_xlabel("Longitud (grados)")
    ax.set_ylabel("Latitud (grados)")
    ax.set_title(
        f"Aerodromo {icao}: grafo de rodaje y rutas de prueba"
    )
    ax.legend(loc="best", fontsize=9, framealpha=0.92)
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, linestyle=":", color="#dddddd", linewidth=0.5)

    suffix = "_strict" if strict else ""
    out = FIG_DIR / f"{icao.lower()}_rutas{suffix}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"[{icao}] Saved: {out}")
    for label, r in results:
        if r.get("success"):
            print(f"  {label}: nodes={len(r['path_node_ids'])} "
                  f"dist={r['total_distance_m']}m taxiways={r['taxiway_sequence']}")
        else:
            print(f"  {label}: FAILED - {r.get('error')}")


def main():
    args = [a for a in sys.argv[1:] if a != "--strict"]
    strict = "--strict" in sys.argv[1:]
    if args:
        icaos = [args[0].upper()]
    else:
        icaos = list(ROUTES.keys())
    for icao in icaos:
        plot_airport(icao, strict=strict)


if __name__ == "__main__":
    main()
