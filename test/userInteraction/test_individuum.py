"""
Visual inspection test: Randomized Individuum

Shows a randomly generated building mass individuum on a 20 × 20 m, 6-floor
building with 2 vertical subtractors and 2 horizontal subtractors.

Display legend:
  - Original building mass (maximal volume)  → faint grey
  - Subtracted building mass                 → transparent white + cyan floor wires
  - Raw subtractor boxes (pre-alignment)     → red wireframe
  - Aligned subtractor boxes (post-grid)     → orange wireframe
  - Building core boxes (full height)        → blue semi-transparent

Run manually (not collected by pytest):
    conda run -n pyoccEnv python test/userInteraction/test_individuum.py

To reproduce the same individuum, set SEED to a fixed integer.
"""
import sys
import os
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from models.individuum import IndividuumParams, Individuum, GENES_PER_SUBTRACTOR
from models.subtractor import SubtractorType

from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.gp import gp_Pnt
from OCC.Core.AIS import AIS_Shape
from OCC.Core.Aspect import Aspect_TOL_DOT, Aspect_TOL_SOLID
from OCC.Core.Prs3d import Prs3d_LineAspect, Prs3d_ShadingAspect
from OCC.Core.Quantity import (
    Quantity_Color,
    Quantity_TOC_RGB,
    Quantity_NOC_WHITE,
    Quantity_NOC_RED,
    Quantity_NOC_GRAY60,
    Quantity_NOC_CYAN1,
)
from OCC.Display.SimpleGui import init_display


# ---------------------------------------------------------------------------
# Individuum definition
# ---------------------------------------------------------------------------

SEED = None   # set to an integer (e.g. 42) for a reproducible result

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

rng = random.Random(SEED)
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

# Collect raw subtractors before alignment (for visualization)
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
# Visualize
# ---------------------------------------------------------------------------

display, start_display, add_menu, add_function_to_menu = init_display()

dark_bg = [8, 8, 25]
display.set_bg_gradient_color(dark_bg, dark_bg)

context = display.Context

white  = Quantity_Color(Quantity_NOC_WHITE)
red    = Quantity_Color(Quantity_NOC_RED)
gray   = Quantity_Color(Quantity_NOC_GRAY60)
cyan   = Quantity_Color(0.2, 0.9, 0.9, Quantity_TOC_RGB)
orange = Quantity_Color(1.0, 0.55, 0.1, Quantity_TOC_RGB)
blue   = Quantity_Color(0.15, 0.45, 1.0, Quantity_TOC_RGB)


# --- Original mass: very faint grey silhouette ---
for floor in original_mass.floors:
    ais = AIS_Shape(floor.solid)
    drawer = ais.Attributes()

    shading = Prs3d_ShadingAspect()
    shading.SetColor(gray)
    shading.SetTransparency(0.97)
    drawer.SetShadingAspect(shading)

    ghost_line = Prs3d_LineAspect(gray, Aspect_TOL_DOT, 0.5)
    drawer.SetWireAspect(ghost_line)
    drawer.SetFaceBoundaryAspect(ghost_line)
    drawer.SetFaceBoundaryDraw(True)

    context.Display(ais, False)
    context.SetDisplayMode(ais, 1, False)


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


# --- Raw subtractor boxes: red wireframe ---
for sub in raw_subtractors:
    box_shape = BRepPrimAPI_MakeBox(
        gp_Pnt(sub.x,             sub.y,             sub.z_bottom),
        gp_Pnt(sub.x + sub.width, sub.y + sub.depth, sub.z_top),
    ).Shape()

    ais_box = AIS_Shape(box_shape)
    box_drawer = ais_box.Attributes()

    box_shading = Prs3d_ShadingAspect()
    box_shading.SetColor(red)
    box_shading.SetTransparency(1.0)
    box_drawer.SetShadingAspect(box_shading)

    red_edge = Prs3d_LineAspect(red, Aspect_TOL_SOLID, 1.0)
    box_drawer.SetWireAspect(red_edge)
    box_drawer.SetFaceBoundaryAspect(red_edge)
    box_drawer.SetFaceBoundaryDraw(True)

    context.Display(ais_box, False)
    context.SetDisplayMode(ais_box, 1, False)


# --- Aligned subtractor boxes: orange wireframe ---
for sub in all_aligned:
    box_shape = BRepPrimAPI_MakeBox(
        gp_Pnt(sub.x,             sub.y,             sub.z_bottom),
        gp_Pnt(sub.x + sub.width, sub.y + sub.depth, sub.z_top),
    ).Shape()

    ais_box = AIS_Shape(box_shape)
    box_drawer = ais_box.Attributes()

    box_shading = Prs3d_ShadingAspect()
    box_shading.SetColor(orange)
    box_shading.SetTransparency(1.0)
    box_drawer.SetShadingAspect(box_shading)

    orange_edge = Prs3d_LineAspect(orange, Aspect_TOL_SOLID, 2.0)
    box_drawer.SetWireAspect(orange_edge)
    box_drawer.SetFaceBoundaryAspect(orange_edge)
    box_drawer.SetFaceBoundaryDraw(True)

    context.Display(ais_box, False)
    context.SetDisplayMode(ais_box, 1, False)


# --- Core boxes: solid blue, semi-transparent, full building height ---
total_height = subtracted_mass.total_height
for core in subtracted_mass.cores:
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


display.FitAll()
start_display()
