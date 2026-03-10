"""
Visual test for HallwayLayout on a 20×20 m floor.

NOT collected by pytest — run manually:
    conda run -n pyoccEnv python test/userInteraction/test_hallway.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

from models.hallway import HallwayLayout, HallwayParams, SkeletonGraph


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

POLYGON = [(0, 0),(0,60), (20,70),(50,70),(50,40),(20,40),(20,0)] #[(0, 0),(0,60), (20,70),(50,70),(50,40),(20,40),(0,40)]
CORE_LOCATIONS = [(10.0, 16.0), (40.0, 55.0)]
PARAMS = HallwayParams(
    floor_polygon=POLYGON,
    elevation=0.0,
    hallway_width=1.8,
    span_x=4.0,
    span_y=4.0,
    core_locations=CORE_LOCATIONS,
    max_travel_distance=80.0,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def plot_shapely_poly(ax, shp, **kwargs):
    if shp.is_empty:
        return
    polys = list(shp.geoms) if hasattr(shp, "geoms") else [shp]
    for p in polys:
        xs, ys = zip(*p.exterior.coords)
        ax.fill(xs, ys, **kwargs)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Computing raw skeleton …")
    raw_skeleton = SkeletonGraph.from_medial_axis(POLYGON)

    print("Generating hallway layout …")
    layout = HallwayLayout.generate(PARAMS)

    print(f"  Hallway area ratio : {layout.hallway_area_ratio():.2%}")
    if CORE_LOCATIONS:
        print(f"  Max travel distance: {layout.max_travel_distance_actual():.2f} m")
    violations = layout.validate()
    print(f"  Violations         : {violations if violations else 'none'}")

    # ------------------------------------------------------------------
    # Plot
    # ------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(9, 9))

    # Floor polygon — grey fill
    xs, ys = zip(*POLYGON, POLYGON[0])
    ax.fill(xs, ys, color="lightgrey", alpha=0.15, zorder=0)
    ax.plot(xs, ys, "k-", linewidth=1.5, zorder=1)

    # Column grid dots
    from shapely.geometry import Point, Polygon as ShapelyPolygon

    floor_shp = ShapelyPolygon(POLYGON)
    ox = min(x for x, _ in POLYGON)
    oy = min(y for _, y in POLYGON)
    mx = max(x for x, _ in POLYGON)
    my = max(y for _, y in POLYGON)
    gx = np.arange(ox, mx + PARAMS.span_x, PARAMS.span_x)
    gy = np.arange(oy, my + PARAMS.span_y, PARAMS.span_y)
    grid_xs, grid_ys = [], []
    for x in gx:
        for y in gy:
            if floor_shp.contains(Point(x, y)) or floor_shp.boundary.distance(Point(x, y)) < 0.1:
                grid_xs.append(x)
                grid_ys.append(y)
    ax.scatter(grid_xs, grid_ys, s=20, color="lightblue", zorder=2, label="Column grid")

    # Raw medial axis — dashed yellow
    for u, v in raw_skeleton.edges:
        ux, uy = raw_skeleton.nodes[u]
        vx, vy = raw_skeleton.nodes[v]
        ax.plot([ux, vx], [uy, vy], "--", color="gold", linewidth=0.8, zorder=3)
    raw_patch = mpatches.Patch(color="gold", linestyle="--", label="Raw medial axis")

    # Final skeleton — solid orange
    for u, v in layout.skeleton.edges:
        ux, uy = layout.skeleton.nodes[u]
        vx, vy = layout.skeleton.nodes[v]
        ax.plot([ux, vx], [uy, vy], "-", color="darkorange", linewidth=2.0, zorder=4)
    skel_patch = mpatches.Patch(color="darkorange", label="Final skeleton")

    # Hallway polygon — semi-transparent red
    plot_shapely_poly(ax, layout.hallway_shp, color="red", alpha=0.35, zorder=5)
    hall_patch = mpatches.Patch(color="red", alpha=0.35, label="Hallway zone")

    # Room zone — semi-transparent green
    room_shp = floor_shp.difference(layout.hallway_shp)
    plot_shapely_poly(ax, room_shp, color="green", alpha=0.25, zorder=4)
    room_patch = mpatches.Patch(color="green", alpha=0.25, label="Room zone")

    # Core locations — solid blue circles
    for cx, cy in CORE_LOCATIONS:
        circle = plt.Circle((cx, cy), 0.5, color="blue", zorder=6)
        ax.add_patch(circle)
    core_patch = mpatches.Patch(color="blue", label="Building cores")

    ax.set_xlim(-1, 100)
    ax.set_ylim(-1, 100)
    ax.set_aspect("equal")
    ax.set_xlabel("X [m]")
    ax.set_ylabel("Y [m]")
    ax.set_title("Hallway Exploration — 20×20 m")
    ax.legend(
        handles=[raw_patch, skel_patch, hall_patch, room_patch, core_patch],
        loc="upper right",
    )
    plt.tight_layout()
    plt.show()
