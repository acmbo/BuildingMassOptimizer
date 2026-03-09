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
from OCC.Core.Aspect import Aspect_TOL_DOT, Aspect_TOL_SOLID
from OCC.Core.Prs3d import Prs3d_LineAspect, Prs3d_ShadingAspect
from OCC.Core.Quantity import (
    Quantity_Color,
    Quantity_TOC_RGB,
    Quantity_NOC_WHITE,
    Quantity_NOC_CYAN1,
)
from OCC.Display.SimpleGui import init_display


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

dark_bg = [8, 8, 25]
display.set_bg_gradient_color(dark_bg, dark_bg)

context = display.Context

white  = Quantity_Color(Quantity_NOC_WHITE)
cyan   = Quantity_Color(Quantity_NOC_CYAN1)
blue   = Quantity_Color(0.15, 0.45, 1.0, Quantity_TOC_RGB)
green  = Quantity_Color(0.2, 0.9, 0.3, Quantity_TOC_RGB)


# --- Subtracted mass: transparent white solids + cyan floor wires ---
for floor in subtracted_mass.floors:
    ais = AIS_Shape(floor.solid)
    drawer = ais.Attributes()

    shading = Prs3d_ShadingAspect()
    shading.SetColor(white)
    shading.SetTransparency(0.82)
    drawer.SetShadingAspect(shading)

    dot_line = Prs3d_LineAspect(white, Aspect_TOL_DOT, 1.2)
    drawer.SetWireAspect(dot_line)
    drawer.SetFaceBoundaryAspect(dot_line)
    drawer.SetFaceBoundaryDraw(True)

    context.Display(ais, False)
    context.SetDisplayMode(ais, 1, False)

    ais_wire = AIS_Shape(floor.polygon_wire)
    wire_drawer = ais_wire.Attributes()
    wire_line = Prs3d_LineAspect(cyan, Aspect_TOL_SOLID, 2.0)
    wire_drawer.SetWireAspect(wire_line)
    context.Display(ais_wire, False)


# --- Core boxes: solid blue, semi-transparent, full building height ---
for core in cores:
    box_shape = BRepPrimAPI_MakeBox(
        gp_Pnt(core.x_min, core.y_min, 0.0),
        gp_Pnt(core.x_max, core.y_max, total_height),
    ).Shape()

    ais_core = AIS_Shape(box_shape)
    core_drawer = ais_core.Attributes()

    core_shading = Prs3d_ShadingAspect()
    core_shading.SetColor(blue)
    core_shading.SetTransparency(0.55)
    core_drawer.SetShadingAspect(core_shading)

    blue_edge = Prs3d_LineAspect(blue, Aspect_TOL_SOLID, 2.0)
    core_drawer.SetWireAspect(blue_edge)
    core_drawer.SetFaceBoundaryAspect(blue_edge)
    core_drawer.SetFaceBoundaryDraw(True)

    context.Display(ais_core, False)
    context.SetDisplayMode(ais_core, 1, False)


# --- Face-midpoint markers: small green boxes at z=0 ---
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


display.FitAll()
start_display()
