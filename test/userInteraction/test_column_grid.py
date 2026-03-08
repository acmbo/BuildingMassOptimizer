"""
Visual test: ColumnGrid overlaid on a 5-sided building mass.

Shows:
  - Building mass floors     white transparent solids, green floor-plan wires
  - Column grid lines        yellow vertical planes (thin boxes) for every X and Y line
  - Column intersection dots cyan thin columns (0.15 × 0.15 × total_height) at each (gx, gy)
  - Unsnapped subtractor     red wireframe box
  - Snapped subtractor       orange wireframe box — faces land on quarter-span positions

Run:
    conda run -n pyoccEnv python test/userInteraction/test_column_grid.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from models import BuildingMass, SpanMode, ColumnGrid, Subtractor, SubtractorType
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.gp import gp_Pnt
from OCC.Core.AIS import AIS_Shape
from OCC.Core.Aspect import Aspect_TOL_DOT, Aspect_TOL_SOLID
from OCC.Core.Prs3d import Prs3d_LineAspect, Prs3d_ShadingAspect
from OCC.Core.Quantity import (
    Quantity_Color, Quantity_TOC_RGB,
    Quantity_NOC_WHITE, Quantity_NOC_RED, Quantity_NOC_CYAN1,
)
from OCC.Display.SimpleGui import init_display

# ---------------------------------------------------------------------------
# Parameters – change here to experiment
# ---------------------------------------------------------------------------

POLYGON = [
    (0, 0, 0),
    (10, 0, 0),
    (10, 6, 0),
    (4, 10, 0),
    (0, 10, 0),
]
FLOOR_HEIGHT = 3.0
NUM_FLOORS   = 5

SPAN_MODE = SpanMode.FIXED_SPAN
SPAN_X    = 4.0   # column spacing X (used for FIXED_SPAN)
SPAN_Y    = 4.0   # column spacing Y (used for FIXED_SPAN)
NX_SPANS  = 3     # used for SPAN_COUNT
NY_SPANS  = 3     # used for SPAN_COUNT

# An unsnapped subtractor — its faces do NOT align with the column grid
RAW_SUB = Subtractor(
    x=1.3, y=2.1, width=4.5, depth=3.7,
    z_bottom=0.0, z_top=FLOOR_HEIGHT * NUM_FLOORS,
    subtractor_type=SubtractorType.VERTICAL,
)

# ---------------------------------------------------------------------------
# Build geometry
# ---------------------------------------------------------------------------

mass = BuildingMass.create(POLYGON, FLOOR_HEIGHT, NUM_FLOORS)

if SPAN_MODE == SpanMode.FIXED_SPAN:
    grid = ColumnGrid.create(mass, SPAN_MODE, span_x=SPAN_X, span_y=SPAN_Y)
else:
    grid = ColumnGrid.create(mass, SPAN_MODE, nx_spans=NX_SPANS, ny_spans=NY_SPANS)

snapped_sub = grid.align_subtractor(RAW_SUB)

print(mass)
print(grid)
print(f"Raw subtractor:     x={RAW_SUB.x}, y={RAW_SUB.y}, "
      f"w={RAW_SUB.width}, d={RAW_SUB.depth}")
if snapped_sub:
    print(f"Snapped subtractor: x={snapped_sub.x}, y={snapped_sub.y}, "
          f"w={snapped_sub.width:.3f}, d={snapped_sub.depth:.3f}")
else:
    print("Snapped subtractor: deactivated (collapsed to zero size)")

# ---------------------------------------------------------------------------
# Display setup
# ---------------------------------------------------------------------------

display, start_display, add_menu, add_function_to_menu = init_display()

dark_bg = [5, 5, 30]
display.set_bg_gradient_color(dark_bg, dark_bg)
context = display.Context

white  = Quantity_Color(Quantity_NOC_WHITE)
green  = Quantity_Color(0.2, 1.0, 0.45, Quantity_TOC_RGB)
yellow = Quantity_Color(1.0, 0.9, 0.0, Quantity_TOC_RGB)
red    = Quantity_Color(Quantity_NOC_RED)
orange = Quantity_Color(1.0, 0.5, 0.0, Quantity_TOC_RGB)
cyan   = Quantity_Color(Quantity_NOC_CYAN1)


def _display_wireframe(shape, colour, transparency=0.95, line_width=1.0):
    ais = AIS_Shape(shape)
    drw = ais.Attributes()
    shd = Prs3d_ShadingAspect()
    shd.SetColor(colour)
    shd.SetTransparency(transparency)
    drw.SetShadingAspect(shd)
    edge = Prs3d_LineAspect(colour, Aspect_TOL_SOLID, line_width)
    drw.SetWireAspect(edge)
    drw.SetFaceBoundaryAspect(edge)
    drw.SetFaceBoundaryDraw(True)
    context.Display(ais, False)
    context.SetDisplayMode(ais, 1, False)
    return ais


# ---------------------------------------------------------------------------
# 1. Building mass — transparent white solids + green floor wires
# ---------------------------------------------------------------------------

for floor in mass.floors:
    ais_solid = AIS_Shape(floor.solid)
    drw = ais_solid.Attributes()
    shd = Prs3d_ShadingAspect()
    shd.SetColor(white)
    shd.SetTransparency(0.88)
    drw.SetShadingAspect(shd)
    dot = Prs3d_LineAspect(white, Aspect_TOL_DOT, 1.0)
    drw.SetWireAspect(dot)
    drw.SetFaceBoundaryAspect(dot)
    drw.SetFaceBoundaryDraw(True)
    context.Display(ais_solid, False)
    context.SetDisplayMode(ais_solid, 1, False)

    ais_wire = AIS_Shape(floor.polygon_wire)
    wire_drw = ais_wire.Attributes()
    wire_line = Prs3d_LineAspect(green, Aspect_TOL_DOT, 2.0)
    wire_drw.SetWireAspect(wire_line)
    context.Display(ais_wire, False)

# ---------------------------------------------------------------------------
# 2. Column grid lines — yellow thin vertical planes
#    Each grid line is rendered as a very thin box spanning full building height
# ---------------------------------------------------------------------------

z_bottom = 0.0
z_top    = mass.total_height
thickness = 0.05  # thin in the perpendicular direction

# X grid lines (YZ planes, thin in X)
for gx in grid.grid_lines_x:
    y0 = grid.origin_y
    y1 = grid.origin_y + grid.total_depth
    box = BRepPrimAPI_MakeBox(
        gp_Pnt(gx - thickness / 2, y0, z_bottom),
        gp_Pnt(gx + thickness / 2, y1, z_top),
    ).Shape()
    _display_wireframe(box, yellow, transparency=0.80, line_width=1.0)

# Y grid lines (XZ planes, thin in Y)
for gy in grid.grid_lines_y:
    x0 = grid.origin_x
    x1 = grid.origin_x + grid.total_width
    box = BRepPrimAPI_MakeBox(
        gp_Pnt(x0, gy - thickness / 2, z_bottom),
        gp_Pnt(x1, gy + thickness / 2, z_top),
    ).Shape()
    _display_wireframe(box, yellow, transparency=0.80, line_width=1.0)

# ---------------------------------------------------------------------------
# 3. Column intersection points — cyan thin columns at each (gx, gy)
# ---------------------------------------------------------------------------

col_size = 0.15
for gx in grid.grid_lines_x:
    for gy in grid.grid_lines_y:
        col = BRepPrimAPI_MakeBox(
            gp_Pnt(gx - col_size / 2, gy - col_size / 2, z_bottom),
            gp_Pnt(gx + col_size / 2, gy + col_size / 2, z_top),
        ).Shape()
        _display_wireframe(col, cyan, transparency=0.0, line_width=1.5)

# ---------------------------------------------------------------------------
# 4. Raw (unsnapped) subtractor — red wireframe
# ---------------------------------------------------------------------------

raw_box = BRepPrimAPI_MakeBox(
    gp_Pnt(RAW_SUB.x, RAW_SUB.y, RAW_SUB.z_bottom),
    gp_Pnt(RAW_SUB.x + RAW_SUB.width, RAW_SUB.y + RAW_SUB.depth, RAW_SUB.z_top),
).Shape()
_display_wireframe(raw_box, red, transparency=0.70, line_width=2.0)

# ---------------------------------------------------------------------------
# 5. Snapped subtractor — orange wireframe
# ---------------------------------------------------------------------------

if snapped_sub:
    snapped_box = BRepPrimAPI_MakeBox(
        gp_Pnt(snapped_sub.x, snapped_sub.y, snapped_sub.z_bottom),
        gp_Pnt(snapped_sub.x + snapped_sub.width,
               snapped_sub.y + snapped_sub.depth,
               snapped_sub.z_top),
    ).Shape()
    _display_wireframe(snapped_box, orange, transparency=0.70, line_width=2.5)

# ---------------------------------------------------------------------------
# Fit and run
# ---------------------------------------------------------------------------

display.FitAll()
start_display()
