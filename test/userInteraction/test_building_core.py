"""
Visual inspection test: Building Cores

Generates a random Individuum on a 20 × 20 m, 6-floor building,
applies find_building_cores(), and displays:
  - Subtracted building mass        → transparent white + cyan floor wires
  - Building core boxes             → solid blue, semi-transparent, full height
  - Face-midpoint markers           → small green boxes at each footprint edge midpoint

Run manually (not collected by pytest):
    conda run -n pyoccEnv python test/userInteraction/test_building_core.py
"""
import sys
import os
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from models.individuum import IndividuumParams, Individuum
from models.column_grid import ColumnGrid
from models.span_mode import SpanMode
from models.building_core_engine import find_building_cores, _extract_face_midpoints

from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.gp import gp_Pnt
from OCC.Core.AIS import AIS_Shape
from OCC.Core.Prs3d import Prs3d_ShadingAspect
from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB
from OCC.Display.SimpleGui import init_display

from visualization.occ_scene import (
    add_building_mass,
    add_cores,
    configure_diagnostic_background,
    configure_isometric_view,
)


# ---------------------------------------------------------------------------
# Build individuum
# ---------------------------------------------------------------------------

SEED = None  # set to an integer for a reproducible result

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

rng = random.Random(SEED)
individuum = Individuum.create_random(params, rng=rng)
_original_mass, subtracted_mass, _config = individuum.build()

# ---------------------------------------------------------------------------
# Find building cores
# ---------------------------------------------------------------------------

column_grid = ColumnGrid.create(
    subtracted_mass, SpanMode.FIXED_SPAN, span_x=params.span_x, span_y=params.span_y
)

MAX_FACE_DISTANCE = 35.0
cores = find_building_cores(subtracted_mass, column_grid, max_face_distance=MAX_FACE_DISTANCE)

# Propagate to mass and floors
subtracted_mass.cores = cores
for floor in subtracted_mass.floors:
    floor.cores = cores

face_midpoints = _extract_face_midpoints(subtracted_mass.floors[0].polygon_wire)

total_height = subtracted_mass.total_height

print("=" * 60)
print(f"Building: 20 × 20 m, {params.num_floors} floors, "
      f"total height {total_height:.1f} m")
print(f"Column grid: {params.span_x} × {params.span_y} m spans")
print(f"max_face_distance: {MAX_FACE_DISTANCE} m")
print(f"Placed {len(cores)} core(s):")
for i, c in enumerate(cores):
    print(f"  Core {i}: {c}")
print(f"Footprint face midpoints: {len(face_midpoints)}")
print("=" * 60)


# ---------------------------------------------------------------------------
# Visualize
# ---------------------------------------------------------------------------

display, start_display, add_menu, add_function_to_menu = init_display()

configure_diagnostic_background(display)

context = display.Context

add_building_mass(context, subtracted_mass, style="DIAGNOSTIC")
add_cores(context, subtracted_mass)

# --- Face-midpoint markers: small green boxes at z=0 (unique to this test) ---
green = Quantity_Color(0.2, 0.9, 0.3, Quantity_TOC_RGB)
MARKER_SIZE = 0.4
for mp in face_midpoints:
    marker = BRepPrimAPI_MakeBox(
        gp_Pnt(mp.x - MARKER_SIZE / 2, mp.y - MARKER_SIZE / 2, -0.1),
        gp_Pnt(mp.x + MARKER_SIZE / 2, mp.y + MARKER_SIZE / 2,  0.1),
    ).Shape()

    ais_mp = AIS_Shape(marker)
    mp_drawer = ais_mp.Attributes()

    mp_shading = Prs3d_ShadingAspect()
    mp_shading.SetColor(green)
    mp_shading.SetTransparency(0.0)
    mp_drawer.SetShadingAspect(mp_shading)

    context.Display(ais_mp, False)
    context.SetDisplayMode(ais_mp, 1, False)


configure_isometric_view(display)
start_display()
