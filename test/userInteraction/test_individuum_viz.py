"""
Visual inspection: Individuum — Isometric view + Per-floor plan grid

Two matplotlib figures are produced, both saved as PNG *and* shown
interactively:

  Figure 1 — Isometric 3D rendering of the subtracted building mass.
             Wall quads and top/bottom caps are drawn as Poly3DCollection.
             The original maximal volume is shown as a faint dashed wireframe
             (disable with --no-original).

  Figure 2 — Grid of 2D floor plan polygons, one subplot per floor.
             Interior voids (courtyards, atriums) are rendered as holes using
             matplotlib.path.Path with reversed sub-path winding.

PNGs are saved alongside this script unless --save-dir is specified.

Run manually (not collected by pytest):
    conda run -n pyoccEnv python test/userInteraction/test_individuum_viz.py
    conda run -n pyoccEnv python test/userInteraction/test_individuum_viz.py --seed 42
    conda run -n pyoccEnv python test/userInteraction/test_individuum_viz.py --no-original
    conda run -n pyoccEnv python test/userInteraction/test_individuum_viz.py --save-dir /tmp
"""

import sys
import os
import math
import random
import argparse

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.path import Path
from matplotlib.patches import PathPatch
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from models.individuum import IndividuumParams, Individuum, GENES_PER_SUBTRACTOR
from models.subtractor import SubtractorType
from models.wire_utils import extract_wire_loops


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

_HERE = os.path.dirname(os.path.abspath(__file__))

parser = argparse.ArgumentParser(
    description="Render a random Individuum as isometric view + floor plan grid."
)
parser.add_argument(
    "--seed", type=int, default=None,
    help="Integer seed for reproducible random individuals (default: random).",
)
parser.add_argument(
    "--no-original", action="store_true",
    help="Hide the original maximal volume wireframe in the isometric view.",
)
parser.add_argument(
    "--save-dir", default=_HERE,
    help="Directory for PNG output (default: same folder as this script).",
)
args = parser.parse_args()

os.makedirs(args.save_dir, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Individuum
# ─────────────────────────────────────────────────────────────────────────────

params = IndividuumParams(
    polygon_points=[
        (0.0,  0.0,  0.0),
        (20.0, 0.0,  0.0),
        (20.0, 20.0, 0.0),
        (0.0,  20.0, 0.0),
    ],
    floor_height=3.5,
    num_floors=6,
    n_vertical=2,
    n_horizontal=2,
    span_x=4.0,
    span_y=4.0,
    min_plan_spans=1.5,
    max_plan_spans=4.0,
    boundary_constraint_enabled=True,
    boundary_snap_fraction=0.10,
    vertical_snap_threshold=0.30,
    horizontal_max_height_ratio=0.30,
)

rng = random.Random(args.seed)
individuum = Individuum.create_random(params, rng=rng)

print("=" * 60)
print(f"Seed: {args.seed}")
print(
    f"Building: {params.bbox_width:.0f} × {params.bbox_depth:.0f} m, "
    f"{params.num_floors} floors × {params.floor_height} m "
    f"= {params.total_height:.1f} m total"
)

original_mass, subtracted_mass, config = individuum.build()

print(
    f"Subtractors: {len(config.vertical_subtractors)} vertical, "
    f"{len(config.horizontal_subtractors)} horizontal (post-constraints)"
)
print("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# Geometry helpers
# ─────────────────────────────────────────────────────────────────────────────

def _wall_quads(
    xy_loop: list[tuple[float, float]],
    z_bot: float,
    z_top: float,
) -> list[list[tuple[float, float, float]]]:
    """One vertical quad per edge of a 2-D polygon loop."""
    quads = []
    n = len(xy_loop)
    for i in range(n):
        j = (i + 1) % n
        x0, y0 = xy_loop[i]
        x1, y1 = xy_loop[j]
        quads.append([
            (x0, y0, z_bot),
            (x1, y1, z_bot),
            (x1, y1, z_top),
            (x0, y0, z_top),
        ])
    return quads


def _cap_polygon(
    xy_loop: list[tuple[float, float]],
    z: float,
) -> list[tuple[float, float, float]]:
    """Elevate a 2-D loop to a horizontal cap polygon at height z."""
    return [(x, y, z) for x, y in xy_loop]


def _build_floor_geometry(floor):
    """
    Return (wall_quads, caps) for one FloorData.

    wall_quads : list of 4-vertex polygons (outer walls + courtyard walls)
    caps       : list of n-vertex polygons (top cap; ground-floor bottom cap)

    Holes (inner loops) contribute wall quads but not caps — the void is
    visible through the open top of the inner walls.
    """
    loops = extract_wire_loops(floor.polygon_wire)
    z_bot = floor.elevation
    z_top = floor.elevation + floor.floor_height

    wall_quads: list = []
    caps: list = []

    for i, loop in enumerate(loops):
        xy = [(p[0], p[1]) for p in loop]
        wall_quads.extend(_wall_quads(xy, z_bot, z_top))

        if i == 0:  # outer loop only contributes horizontal caps
            caps.append(_cap_polygon(xy, z_top))
            if floor.index == 0:
                caps.append(_cap_polygon(xy, z_bot))

    return wall_quads, caps


def _original_volume_edges(mass):
    """
    Yield (xs, ys, zs) line-segment tuples for the bounding box wireframe of
    the maximal volume (vertical corner edges + top and bottom perimeter).
    """
    pts = mass.polygon_points
    n = len(pts)
    H = mass.total_height

    # Vertical corner edges
    for x, y, _ in pts:
        yield [x, x], [y, y], [0.0, H]

    # Horizontal perimeter at bottom and top
    for z in (0.0, H):
        for i in range(n):
            j = (i + 1) % n
            x0, y0, _ = pts[i]
            x1, y1, _ = pts[j]
            yield [x0, x1], [y0, y1], [z, z]


# ─────────────────────────────────────────────────────────────────────────────
# Figure 1 — Isometric 3D rendering
# ─────────────────────────────────────────────────────────────────────────────

# Colour palette
_WALL_FACE   = "#ddeeff"   # outer / courtyard wall fill
_WALL_EDGE   = "#2a3a4a"   # wall edges
_CAP_FACE    = "#f5f9ff"   # top cap fill (slightly lighter)
_BOT_FACE    = "#b0c4d8"   # ground bottom cap
_ORIG_COLOR  = "#9aabba"   # original volume wireframe

fig_iso = plt.figure(figsize=(11, 10), facecolor="#ffffff")
ax_iso: plt.Axes = fig_iso.add_subplot(111, projection="3d")
ax_iso.set_facecolor("#f7f9fb")

all_walls: list = []
all_caps:  list = []
all_bot:   list = []

for floor in subtracted_mass.floors:
    walls, caps = _build_floor_geometry(floor)
    # Separate top caps from bottom caps (bottom only on ground floor)
    all_walls.extend(walls)
    for cap in caps:
        if cap[0][2] == 0.0:            # z == 0 → ground bottom cap
            all_bot.append(cap)
        else:
            all_caps.append(cap)

if all_walls:
    ax_iso.add_collection3d(Poly3DCollection(
        all_walls, closed=True,
        facecolor=_WALL_FACE, edgecolor=_WALL_EDGE,
        linewidth=0.5, alpha=0.88,
    ))

if all_caps:
    ax_iso.add_collection3d(Poly3DCollection(
        all_caps, closed=True,
        facecolor=_CAP_FACE, edgecolor=_WALL_EDGE,
        linewidth=0.5, alpha=0.95,
    ))

if all_bot:
    ax_iso.add_collection3d(Poly3DCollection(
        all_bot, closed=True,
        facecolor=_BOT_FACE, edgecolor=_WALL_EDGE,
        linewidth=0.5, alpha=0.90,
    ))

# Original maximal volume — faint dashed wireframe
if not args.no_original:
    for xs, ys, zs in _original_volume_edges(original_mass):
        ax_iso.plot(
            xs, ys, zs,
            color=_ORIG_COLOR, linewidth=0.9,
            linestyle="--", alpha=0.45, zorder=0,
        )

# True isometric camera angles
ax_iso.view_init(elev=35.264, azim=45)

W = params.bbox_width
D = params.bbox_depth
H = params.total_height

ax_iso.set_xlim(0, W)
ax_iso.set_ylim(0, D)
ax_iso.set_zlim(0, H)
ax_iso.set_box_aspect([W, D, H])

ax_iso.set_xlabel("X (m)", labelpad=8, fontsize=9)
ax_iso.set_ylabel("Y (m)", labelpad=8, fontsize=9)
ax_iso.set_zlabel("Z (m)", labelpad=8, fontsize=9)
ax_iso.tick_params(labelsize=8)

ax_iso.set_title(
    f"Building Mass — Isometric View   "
    f"(seed={args.seed}, "
    f"{len(config.vertical_subtractors)}V + {len(config.horizontal_subtractors)}H subtractors)",
    pad=14, fontsize=11,
)

iso_path = os.path.join(args.save_dir, "individuum_iso.png")
fig_iso.savefig(iso_path, dpi=150, bbox_inches="tight")
print(f"Saved: {iso_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Figure 2 — Per-floor plan grid
# ─────────────────────────────────────────────────────────────────────────────

def _make_floor_path(loops: list[list[tuple]]) -> Path:
    """
    Build a matplotlib Path for a floor polygon that may contain holes.

    Each loop is a separate sub-path (MOVETO … LINETO … CLOSEPOLY).
    Hole loops (index > 0) are reversed so their winding direction is
    opposite to the outer boundary.  Combined with matplotlib's nonzero
    winding rule this correctly punches voids through the fill.
    """
    verts: list = []
    codes: list = []

    for i, loop in enumerate(loops):
        xy = [(p[0], p[1]) for p in loop]
        if i > 0:
            xy = list(reversed(xy))   # opposite winding → acts as hole

        for j, pt in enumerate(xy):
            verts.append(pt)
            codes.append(Path.MOVETO if j == 0 else Path.LINETO)

        verts.append(xy[0])
        codes.append(Path.CLOSEPOLY)

    return Path(np.array(verts, dtype=float), codes)


num_floors = len(subtracted_mass.floors)
n_cols = min(3, num_floors)
n_rows = math.ceil(num_floors / n_cols)

fig_floors, axes = plt.subplots(
    n_rows, n_cols,
    figsize=(4.5 * n_cols, 4.5 * n_rows),
    squeeze=False,
    facecolor="#ffffff",
)
fig_floors.suptitle(
    f"Per-floor Plan Polygons   (seed={args.seed})",
    fontsize=13, y=1.02,
)

# Shared axis limits with a small margin
_MARGIN = 1.5
_XLIM = (params.bbox_xmin - _MARGIN, params.bbox_xmax + _MARGIN)
_YLIM = (params.bbox_ymin - _MARGIN, params.bbox_ymax + _MARGIN)

# Pre-build a Path for the original footprint (used as void background in every subplot)
_orig_pts = [(p[0], p[1]) for p in params.polygon_points]
_orig_path = Path(
    np.array(_orig_pts + [_orig_pts[0]], dtype=float),
    [Path.MOVETO] + [Path.LINETO] * (len(_orig_pts) - 1) + [Path.CLOSEPOLY],
)

for idx, floor in enumerate(subtracted_mass.floors):
    row, col = divmod(idx, n_cols)
    ax = axes[row][col]

    ax.set_facecolor("#f0f4f8")
    ax.set_aspect("equal")
    ax.set_xlim(*_XLIM)
    ax.set_ylim(*_YLIM)
    ax.tick_params(labelsize=7)
    ax.set_xlabel("X (m)", fontsize=7, labelpad=3)
    ax.set_ylabel("Y (m)", fontsize=7, labelpad=3)

    # Layer 1 — original footprint filled with "void" colour.
    # This makes subtracted areas visually distinct: anything not covered by
    # the solid floor patch below shows as void (pink/salmon).
    ax.add_patch(PathPatch(
        _orig_path,
        facecolor="#f5d0cc",   # light salmon = void / subtracted material
        edgecolor="#cc6655",
        linewidth=1.0,
        linestyle="--",
        zorder=1,
    ))

    # Layer 2 — remaining solid floor area on top.
    # Interior holes (courtyards) are punched through via reversed winding,
    # letting the void colour show through.
    loops = extract_wire_loops(floor.polygon_wire)
    if loops:
        patch = PathPatch(
            _make_floor_path(loops),
            facecolor="#b8d4f0",   # blue = solid floor material
            edgecolor="#1e4080",
            linewidth=1.2,
            zorder=2,
        )
        ax.add_patch(patch)

    ax.set_title(
        f"Floor {floor.index}   z = {floor.elevation:.1f} m",
        fontsize=9, pad=5,
    )

# Hide unused subplots
for idx in range(num_floors, n_rows * n_cols):
    row, col = divmod(idx, n_cols)
    axes[row][col].set_visible(False)

fig_floors.tight_layout()
floors_path = os.path.join(args.save_dir, "individuum_floors.png")
fig_floors.savefig(floors_path, dpi=150, bbox_inches="tight")
print(f"Saved: {floors_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Show both figures interactively
# ─────────────────────────────────────────────────────────────────────────────

plt.show()
