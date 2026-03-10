"""
Visual inspection: Individuum — OCC 3D view + Architectural floor plan grid

Two outputs are produced:

  3D view (OCC) — Isometric render of the building mass.
    Style is controlled by --mode:
      diagnostic    Semi-transparent white mass + cyan floor wires + subtractor
                    boxes (red raw, orange aligned) + blue core boxes.
                    Original maximal volume shown as a faint ghost (disable
                    with --no-original).
      architectural White opaque plaster mass + white ground plane +
                    directional light + ray-traced shadows and ambient
                    occlusion.  No wires or subtractor boxes.
    Rendering mode is controlled by --headless:
      (default)     Opens an interactive OCC/Tkinter viewer.
                    Add --save to also export a PNG without closing the viewer.
      --headless    No window is opened.  A PNG is written directly to
                    --save-dir using an offscreen OpenGL context.
                    If the offscreen context fails, a Xvfb fallback command
                    is printed.

  Floor plan grid (matplotlib) — One architectural section-cut plan per floor.
    Always saved as 'individuum_floors.png' and shown (non-blocking before
    the OCC viewer opens).

PNGs are saved to --save-dir (default: folder of this script).

Run manually (not collected by pytest):
    conda run -n pyoccEnv python test/userInteraction/test_individuum_viz.py
    conda run -n pyoccEnv python test/userInteraction/test_individuum_viz.py --seed 42
    conda run -n pyoccEnv python test/userInteraction/test_individuum_viz.py --mode architectural
    conda run -n pyoccEnv python test/userInteraction/test_individuum_viz.py --headless --save-dir /tmp
    conda run -n pyoccEnv python test/userInteraction/test_individuum_viz.py --no-original --save-dir /tmp
"""

import sys
import os
import random
import argparse

import matplotlib.pyplot as plt

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


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(
    description="Render a random Individuum: OCC 3D view + floor plan grid."
)
parser.add_argument(
    "--seed", type=int, default=None,
    help="Integer seed for reproducible random individuals (default: random).",
)
parser.add_argument(
    "--mode", choices=["diagnostic", "architectural"], default="architectural",
    help="3D render style (default: architectural).",
)
parser.add_argument(
    "--no-original", action="store_true",
    help="Hide the original maximal volume ghost in diagnostic mode.",
)
parser.add_argument(
    "--headless", action="store_true",
    help="Render 3D PNG headlessly (no OCC viewer window).",
)
parser.add_argument(
    "--save-dir", default=_HERE,
    help="Directory for PNG output (default: same folder as this script).",
)
args = parser.parse_args()

os.makedirs(args.save_dir, exist_ok=True)
STYLE = args.mode.upper()


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
    core_generation_enabled=True,
    max_face_distance=35.0,
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

# Collect raw subtractors before alignment (needed for diagnostic mode)
raw_subtractors = []
for k in range(params.n_vertical):
    raw_subtractors.append(individuum._decode_subtractor(k, SubtractorType.VERTICAL))
for k in range(params.n_horizontal):
    raw_subtractors.append(
        individuum._decode_subtractor(params.n_vertical + k, SubtractorType.HORIZONTAL)
    )

original_mass, subtracted_mass, config = individuum.build()

print(
    f"Subtractors: {len(config.vertical_subtractors)} vertical, "
    f"{len(config.horizontal_subtractors)} horizontal (post-constraints)"
)
print(f"Cores: {len(subtracted_mass.cores)}")
for i, c in enumerate(subtracted_mass.cores):
    print(f"  Core {i}: {c}")
print("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# Figure 1 — Architectural floor plan grid (matplotlib, non-blocking)
# ─────────────────────────────────────────────────────────────────────────────

col_grid = ColumnGrid.create(
    subtracted_mass,
    SpanMode.FIXED_SPAN,
    span_x=params.span_x,
    span_y=params.span_y,
)
orig_footprint = [(p[0], p[1]) for p in params.polygon_points]

floors_path = os.path.join(args.save_dir, "individuum_floors.png")
fig_floors = draw_floor_plan_grid(
    subtracted_mass.floors,
    column_grid=col_grid,
    original_footprint=orig_footprint,
    n_cols=3,
    subplot_size=4.5,
    title=f"Architectural Floor Plans   (seed={args.seed}, "
          f"{len(config.vertical_subtractors)}V + "
          f"{len(config.horizontal_subtractors)}H subtractors, "
          f"{len(subtracted_mass.cores)} cores)",
    show_column_labels=True,
    show_scale_bar=True,
    show_north_arrow=True,
    save_path=floors_path,
)
print(f"Saved: {floors_path}")

plt.show(block=False)
plt.pause(0.2)


# ─────────────────────────────────────────────────────────────────────────────
# Figure 2 — OCC 3D view
# ─────────────────────────────────────────────────────────────────────────────

iso_path = os.path.join(args.save_dir, f"individuum_iso_{args.mode}.png")

if args.headless:
    # ── Headless: offscreen PNG, no window ───────────────────────────────────
    print(f"Rendering headless ({STYLE}) → {iso_path}")
    render_png(
        subtracted_mass,
        iso_path,
        style=STYLE,
        headless=True,
        config=config if STYLE == "DIAGNOSTIC" else None,
        raw_subtractors=raw_subtractors if STYLE == "DIAGNOSTIC" else None,
    )

else:
    # ── Interactive: open OCC viewer, optionally export PNG ──────────────────
    from OCC.Display.SimpleGui import init_display

    display, start_display, _add_menu, _add_fn = init_display()
    context = display.Context

    if STYLE == "ARCHITECTURAL":
        configure_architectural_background(display)
        add_building_mass(context, subtracted_mass, style="ARCHITECTURAL")
        add_ground_plane(context, subtracted_mass, style="ARCHITECTURAL")
        add_directional_light(display)
        configure_ray_tracing(display)
    else:  # DIAGNOSTIC
        configure_diagnostic_background(display)
        if not args.no_original:
            add_original_mass(context, original_mass)
        add_building_mass(context, subtracted_mass, style="DIAGNOSTIC")
        add_subtractors(context, config, raw=raw_subtractors)
        add_cores(context, subtracted_mass)

    configure_isometric_view(display)

    # Always export PNG alongside the floor plans
    export_png(display, iso_path)
    print(f"Saving on first frame: {iso_path}")

    start_display()
