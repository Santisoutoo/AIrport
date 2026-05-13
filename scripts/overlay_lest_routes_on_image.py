"""Overlay the three LEST taxi routes on a real X-Plane screenshot.

Uses 4 calibration points to compute a homography from (lon, lat) to (px, py)
and draws each route as a coloured polyline on top of image.png.

If the routes do not fall on top of the actual taxiways/runway in the
resulting PNG, adjust CALIBRATION below. Each entry pairs a geographic
coordinate (longitude, latitude) — taken from LEST_graph.json or from the
runway thresholds — with the pixel where it appears on the screenshot.
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from plugins.GND.graph import AirportGraph


IMG_IN = Path(
    r"c:/Users/santi/Documents/documentos_tfg/memoria/"
    r"capitulos/05_resultados/cap/image.png"
)
IMG_OUT = Path(
    r"c:/Users/santi/Documents/documentos_tfg/memoria/"
    r"capitulos/05_resultados/cap/image_with_routes.png"
)
GRAPH_JSON = Path("data/airport_data/LEST/LEST_graph.json")


# ---- Calibration points -----------------------------------------------------
#
# 4 (lon, lat) -> (px, py) pairs. The picture is an oblique aerial view
# looking roughly north, so we use points spread over the visible area:
#   1. Runway-17 threshold (top of the runway, far end in the picture)
#   2. Runway-17 stop bar / first taxiway exit area (the marked turn-off)
#   3. Centre of the small commercial apron, NE corner of cargo hangars
#   4. Centre of the T-shaped passenger terminal apron
#
# Pixel coordinates are FIRST-PASS estimates eyeballed from the 1547x1019
# image — if the routes look mis-aligned, tweak them.
CALIBRATION = [
    # (lon,         lat,        px,    py)   ← edit if alignment is off
    (-8.42033176, 42.91180046,  550,   60),   # RWY 17 threshold — far end on horizon
    (-8.41094228, 42.88381103, 1500,  900),   # RWY 35 threshold — extrapolated, off-frame SE
    (-8.41920889, 42.89347487,  340,  430),   # stand 11 — GA apron centre
    (-8.41854799, 42.89546741,  410,  370),   # stand 19 — GA apron, north of stand 11
]


def compute_homography(pairs):
    """Compute the 3x3 homography mapping (lon, lat) -> (px, py).

    Uses the standard DLT with SVD. Expects >=4 (lon, lat, px, py) tuples.
    """
    A = []
    for lon, lat, px, py in pairs:
        X, Y = lon, lat
        A.append([-X, -Y, -1, 0, 0, 0, px * X, px * Y, px])
        A.append([0, 0, 0, -X, -Y, -1, py * X, py * Y, py])
    A = np.array(A, dtype=np.float64)
    _, _, Vt = np.linalg.svd(A)
    h = Vt[-1]
    H = h.reshape(3, 3)
    return H / H[2, 2]


def project(H, lon, lat):
    """Map a single (lon, lat) to (px, py) via H."""
    v = H @ np.array([lon, lat, 1.0])
    return v[0] / v[2], v[1] / v[2]


def main():
    g = AirportGraph(str(GRAPH_JSON))
    img = Image.open(IMG_IN).convert("RGBA")

    H = compute_homography(CALIBRATION)
    print("Homography:")
    print(H)

    # Verify calibration error
    print("\nCalibration residuals (pixels):")
    for lon, lat, px, py in CALIBRATION:
        ppx, ppy = project(H, lon, lat)
        print(f"  ({lon:.5f},{lat:.5f}) -> ({ppx:7.1f},{ppy:7.1f})  "
              f"target=({px},{py})  err=({ppx-px:+.1f},{ppy-py:+.1f})")

    # Compute the three routes (same as figure script)
    routes = [
        ("Stand 11 -> RWY 35 (directa)", "#2e7d32",
         g.find_route_from_position(42.89347487, -8.41920889, "35")),
        ("Stand 11 -> RWY 35 via E1", "#c62828",
         g.find_route_from_position(42.89347487, -8.41920889, "35", via=["E1"])),
        ("Stand 19 -> RWY 17", "#1565c0",
         g.find_route_from_position(42.89546741, -8.41854799, "17")),
    ]

    # Draw the underlying taxi graph faintly first
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # (Background graph removed — keeps the overlay clean to compare routes
    # against the visible taxiways.)

    # Routes
    for label, hex_color, r in routes:
        if not r.get("success"):
            print(f"  SKIP {label}: {r.get('error')}")
            continue
        # Hex to RGBA
        c = tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5)) + (235,)
        pts = []
        for nid in r["path_node_ids"]:
            n = g.graph.nodes[nid]
            pts.append(project(H, n["lon"], n["lat"]))
        draw.line(pts, fill=c, width=6)
        # Markers at start and end
        draw.ellipse(
            [pts[0][0] - 9, pts[0][1] - 9, pts[0][0] + 9, pts[0][1] + 9],
            fill=c, outline=(255, 255, 255, 255), width=2,
        )
        draw.ellipse(
            [pts[-1][0] - 9, pts[-1][1] - 9, pts[-1][0] + 9, pts[-1][1] + 9],
            fill=c, outline=(255, 255, 255, 255), width=2,
        )

    # Legend top-right
    legend_x, legend_y = img.size[0] - 380, 30
    pad = 8
    line_h = 32
    draw.rectangle(
        [legend_x - pad, legend_y - pad,
         legend_x + 370, legend_y + line_h * len(routes) + pad],
        fill=(0, 0, 0, 170),
    )
    for i, (label, hex_color, _) in enumerate(routes):
        c = tuple(int(hex_color[i_:i_ + 2], 16) for i_ in (1, 3, 5)) + (255,)
        y = legend_y + i * line_h
        draw.line([(legend_x, y + 14), (legend_x + 50, y + 14)],
                  fill=c, width=6)
        draw.text((legend_x + 60, y + 4), label, fill=(255, 255, 255, 255))

    out = Image.alpha_composite(img, overlay)
    IMG_OUT.parent.mkdir(parents=True, exist_ok=True)
    out.convert("RGB").save(IMG_OUT, "PNG")
    print(f"\nSaved: {IMG_OUT}")


if __name__ == "__main__":
    main()
