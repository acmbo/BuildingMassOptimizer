"""
Visual inspection test: Subtractive Form Generation

Shows a 10x10 m, 5-floor building with three subtractors applied:
  1. Vertical subtractor — central courtyard (spans full height)
  2. Vertical subtractor — corner notch (open boundary, snapped through wall)
  3. Horizontal subtractor — stilts at ground level

Display legend:
  - Original building mass    → very faint grey (background reference)
  - Subtracted building mass  → transparent white solid + cyan floor wires
  - Subtractor boxes          → red wireframe

Run manually (not collected by pytest):
    conda run -n pyoccEnv python test/userInteraction/test_subtraction.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from models import BuildingMass
from models.subtractor import Subtractor, SubtractorType, SubtractionConfig
from models.subtraction_engine import apply_subtractions

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
)
from OCC.Display.SimpleGui import init_display


# ---------------------------------------------------------------------------
# Building definition
# ---------------------------------------------------------------------------

polygon_points = [
    (0, 0, 0),
    (10, 0, 0),
    (10, 10, 0),
    (0, 10, 0),
]
floor_height = 3.0
num_floors = 5
total_height = floor_height * num_floors  # 15.0

original_mass = BuildingMass.create(polygon_points, floor_height, num_floors)

# ---------------------------------------------------------------------------
# Subtraction configuration
# ---------------------------------------------------------------------------

# 1. Central courtyard: vertical subtractor spanning (almost) full height.
#    Both faces are within 30% of 15m = 4.5m → both snap → full courtyard.
courtyard = Subtractor(
    x=3.0, y=3.0,
    width=4.0, depth=4.0,
    z_bottom=0.5,   # gap = 0.5 < 4.5 → snaps to 0
    z_top=14.5,     # gap = 0.5 < 4.5 → snaps to 15
    subtractor_type=SubtractorType.VERTICAL,
)

# 2. Corner notch: vertical subtractor at one corner with open boundary.
#    z_bottom close to 0 → snaps; z_top close to total_height → snaps.
#    boundary_constraint_enabled=False lets it break through the outer wall.
corner_notch = Subtractor(
    x=8.5, y=8.5,   # close to x=10, y=10 corner
    width=2.5, depth=2.5,
    z_bottom=0.2,    # gap < 4.5 → snaps to 0
    z_top=14.8,      # gap < 4.5 → snaps to 15
    subtractor_type=SubtractorType.VERTICAL,
)

# 3. Stilts: horizontal subtractor at ground level (z=0..3), full footprint
#    but only 1 floor tall → creates a void at the base (building on stilts).
stilts = Subtractor(
    x=1.5, y=0.0,
    width=7.0, depth=10.0,
    z_bottom=0.0,
    z_top=floor_height,   # exactly 1 floor tall — within horizontal height range
    subtractor_type=SubtractorType.HORIZONTAL,
)

config = SubtractionConfig(
    vertical_subtractors=[courtyard, corner_notch],
    horizontal_subtractors=[stilts],
    vertical_snap_threshold=0.30,
    horizontal_max_height_ratio=0.30,
    boundary_constraint_enabled=False,   # corner notch breaks through the wall
    boundary_snap_fraction=0.10,
)

subtracted_mass = apply_subtractions(original_mass, config)

print(f"Original:   {original_mass}")
print(f"Subtracted: {subtracted_mass}")
print(f"Active subtractors: courtyard + corner_notch + stilts")

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


# --- Subtractor boxes: red wireframe ---
all_subtractors = config.vertical_subtractors + config.horizontal_subtractors
for sub in all_subtractors:
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

    red_edge = Prs3d_LineAspect(red, Aspect_TOL_SOLID, 1.5)
    box_drawer.SetWireAspect(red_edge)
    box_drawer.SetFaceBoundaryAspect(red_edge)
    box_drawer.SetFaceBoundaryDraw(True)

    context.Display(ais_box, False)
    context.SetDisplayMode(ais_box, 1, False)


display.FitAll()
start_display()
