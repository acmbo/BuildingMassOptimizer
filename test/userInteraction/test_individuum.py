"""
Visual inspection test: Randomized Individuum

Shows a randomly generated building mass individuum on a 20 × 20 m, 6-floor
building with 2 vertical subtractors and 2 horizontal subtractors.

Two outputs are produced:

  Matplotlib (non-blocking) — Architectural floor plan grid showing one
    section-cut plan per floor with column grid, hatch, cores, scale bar.
    Saved as 'individuum_floors.png' alongside this script.

  OCC 3D viewer — Isometric 3D view controlled by --mode:
    diagnostic    (default) Semi-transparent white + cyan wires + subtractor
                  boxes (red raw / orange aligned) + blue core boxes.
                  Original maximal volume shown as a faint grey ghost.
    architectural White opaque plaster mass + ground plane + directional
                  light + ray-traced shadows.

  Rendering mode:
    (default)     Interactive OCC/Tkinter viewer (blocking).
                  Add --save to also export a PNG without closing the viewer.
    --headless    No window is opened.  A PNG is written using an offscreen
                  OpenGL context.  If the offscreen context fails, a Xvfb
                  fallback command is printed.

Run manually (not collected by pytest):
    conda run -n pyoccEnv python test/userInteraction/test_individuum.py
    conda run -n pyoccEnv python test/userInteraction/test_individuum.py --seed 42
    conda run -n pyoccEnv python test/userInteraction/test_individuum.py --mode architectural
    conda run -n pyoccEnv python test/userInteraction/test_individuum.py --headless --save /tmp/out.png
"""
import sys
import os
import random
import argparse

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "src"))

from models.individuum import IndividuumParams, Individuum, GENES_PER_SUBTRACTOR
from models.subtractor import SubtractorType
from models.column_grid import ColumnGrid
from models.span_mode import SpanMode
from visualization import draw_floor_plan_grid
from visualization.occ_scene import (
    add_building_mass,
    add_original_mass,
    add_subtractors,
    add_cores,
    add_ground_plane,
    add_directional_light,
    configure_diagnostic_background,
    configure_architectural_background,
    configure_isometric_view,
    configure_ray_tracing,
    export_png,
    render_png,
)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(
    description="Render a random Individuum: floor plan grid + OCC 3D view."
)
parser.add_argument(
    "--seed", type=int, default=None,
    help="Integer seed for reproducible result (default: random).",
)
parser.add_argument(
    "--mode", choices=["diagnostic", "architectural"], default="diagnostic",
    help="3D render style (default: diagnostic).",
)
parser.add_argument(
    "--headless", action="store_true",
    help="Render 3D PNG headlessly (no OCC viewer window).",
)
parser.add_argument(
    "--save", default=None, metavar="PATH",
    help="Export OCC view to PNG at this path (interactive mode only).",
)
args = parser.parse_args()

STYLE = args.mode.upper()

# Default PNG path when --headless is used without --save
if args.headless and args.save is None:
    args.save = os.path.join(_HERE, "individuum_3d.png")


# ---------------------------------------------------------------------------
# Individuum definition
# ---------------------------------------------------------------------------

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
    core_generation_enabled=True,
    max_face_distance=35.0,
)

rng = random.Random(args.seed)
individuum = Individuum.create_random(params, rng=rng)

print("=" * 60)
print("IndividuumParams:")
print(f"  building:    {params.bbox_width:.1f} x {params.bbox_depth:.1f} m, "
      f"{params.num_floors} floors x {params.floor_height} m = "
      f"{params.total_height:.1f} m total")
print(f"  subtractors: {params.n_vertical} vertical + {params.n_horizontal} horizontal")
print(f"  column grid: {params.span_x} x {params.span_y} m spans")
print(f"  plan size:   {params.min_plan_size:.1f} – {params.max_plan_size:.1f} m")
print()
print("Genome:")
for k in range(params.n_vertical + params.n_horizontal):
    sub_type = "V" if k < params.n_vertical else "H"
    g = individuum.genome[k * GENES_PER_SUBTRACTOR : (k + 1) * GENES_PER_SUBTRACTOR]
    print(f"  [{sub_type}{k}] x={g[0]:.3f} y={g[1]:.3f} "
          f"w={g[2]:.3f} d={g[3]:.3f} "
          f"z_bot={g[4]:.3f} z_top={g[5]:.3f}")
print()

# Collect raw subtractors before alignment (for diagnostic visualization)
raw_subtractors = []
for k in range(params.n_vertical):
    raw_subtractors.append(individuum._decode_subtractor(k, SubtractorType.VERTICAL))
for k in range(params.n_horizontal):
    raw_subtractors.append(
        individuum._decode_subtractor(params.n_vertical + k, SubtractorType.HORIZONTAL)
    )

original_mass, subtracted_mass, config = individuum.build()

all_aligned = config.vertical_subtractors + config.horizontal_subtractors

print(f"Active subtractors after alignment + constraints: {len(all_aligned)}")
print(f"  vertical:   {len(config.vertical_subtractors)}")
print(f"  horizontal: {len(config.horizontal_subtractors)}")
print()
print(f"Original mass:   {original_mass}")
print(f"Subtracted mass: {subtracted_mass}")
print(f"Building cores:  {len(subtracted_mass.cores)}")
for i, c in enumerate(subtracted_mass.cores):
    print(f"  Core {i}: {c}")
print("=" * 60)


# ---------------------------------------------------------------------------
# Figure 1 — Architectural floor plan grid (matplotlib, non-blocking)
# ---------------------------------------------------------------------------

import matplotlib.pyplot as plt

col_grid = ColumnGrid.create(
    subtracted_mass,
    SpanMode.FIXED_SPAN,
    span_x=params.span_x,
    span_y=params.span_y,
)
orig_footprint = [(p[0], p[1]) for p in params.polygon_points]

floors_png = os.path.join(_HERE, "individuum_floors.png")
fig_floors = draw_floor_plan_grid(
    subtracted_mass.floors,
    column_grid=col_grid,
    original_footprint=orig_footprint,
    n_cols=3,
    subplot_size=4.5,
    title=(
        f"Architectural Floor Plans   "
        f"({len(config.vertical_subtractors)}V + "
        f"{len(config.horizontal_subtractors)}H subtractors, "
        f"{len(subtracted_mass.cores)} cores)"
    ),
    show_column_labels=True,
    show_scale_bar=True,
    show_north_arrow=True,
    save_path=floors_png,
)
print(f"Saved: {floors_png}")

# Show non-blocking so the OCC viewer can open immediately after
plt.show(block=False)
plt.pause(0.2)


# ---------------------------------------------------------------------------
# Figure 2 — OCC 3D view
# ---------------------------------------------------------------------------

if args.headless:
    # ── Headless: offscreen PNG, no window ───────────────────────────────────
    print(f"Rendering headless ({STYLE}) → {args.save}")
    render_png(
        subtracted_mass,
        args.save,
        style=STYLE,
        headless=True,
        config=config if STYLE == "DIAGNOSTIC" else None,
        raw_subtractors=raw_subtractors if STYLE == "DIAGNOSTIC" else None,
    )

else:
    # ── Interactive: open OCC viewer, optionally export PNG ──────────────────
    from OCC.Display.SimpleGui import init_display

    display, start_display, add_menu, add_function_to_menu = init_display()
    context = display.Context

    if STYLE == "ARCHITECTURAL":
        configure_architectural_background(display)
        add_building_mass(context, subtracted_mass, style="ARCHITECTURAL")
        add_ground_plane(context, subtracted_mass, style="ARCHITECTURAL")
        add_directional_light(display)
        configure_ray_tracing(display)
    else:  # DIAGNOSTIC
        configure_diagnostic_background(display)
        add_original_mass(context, original_mass)
        add_building_mass(context, subtracted_mass, style="DIAGNOSTIC")
        add_subtractors(context, config, raw=raw_subtractors)
        add_cores(context, subtracted_mass)

    configure_isometric_view(display)

    if args.save:
        export_png(display, args.save)
        print(f"Saving on first frame: {args.save}")

    start_display()
