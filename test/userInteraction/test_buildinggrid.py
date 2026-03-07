import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from models import BuildingMass, BuildingGrid, CellMode
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.gp import gp_Pnt
from OCC.Core.AIS import AIS_Shape
from OCC.Core.Aspect import Aspect_TOL_DOT, Aspect_TOL_SOLID
from OCC.Core.Prs3d import Prs3d_LineAspect, Prs3d_ShadingAspect
from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB, Quantity_NOC_WHITE, Quantity_NOC_RED
from OCC.Display.SimpleGui import init_display

# --- User inputs ---
polygon_points = [
    (0, 0, 0),
    (10, 0, 0),
    (10, 6, 0),
    (4, 10, 0),
    (0, 10, 0),
]
floor_height = 3.0
num_floors = 5

# --- Change grid mode here ---
CELL_MODE = CellMode.FIXED_SIZE
CELL_SIZE = 2.0        # used when CELL_MODE = FIXED_SIZE
CELL_COUNT = 6         # used when CELL_MODE = CELL_COUNT

# --- Generate building mass and grid ---
mass = BuildingMass.create(polygon_points, floor_height, num_floors)

if CELL_MODE == CellMode.FIXED_SIZE:
    grid = BuildingGrid.create(mass, CELL_MODE, cell_size=CELL_SIZE)
else:
    grid = BuildingGrid.create(mass, CELL_MODE, cell_count=CELL_COUNT)

print(mass)
print(grid)

# --- Visualize ---
display, start_display, add_menu, add_function_to_menu = init_display()

dark_blue_rgb = [5, 5, 30]
display.set_bg_gradient_color(dark_blue_rgb, dark_blue_rgb)

context = display.Context
white = Quantity_Color(Quantity_NOC_WHITE)
green = Quantity_Color(0.2, 1.0, 0.45, Quantity_TOC_RGB)
red   = Quantity_Color(Quantity_NOC_RED)

# --- Building mass: transparent white solids + green floor wires ---
for floor in mass.floors:
    ais = AIS_Shape(floor.solid)
    drawer = ais.Attributes()

    shading = Prs3d_ShadingAspect()
    shading.SetColor(white)
    shading.SetTransparency(0.88)
    drawer.SetShadingAspect(shading)

    dot_line = Prs3d_LineAspect(white, Aspect_TOL_DOT, 1.5)
    drawer.SetWireAspect(dot_line)
    drawer.SetFaceBoundaryAspect(dot_line)
    drawer.SetFaceBoundaryDraw(True)

    context.Display(ais, False)
    context.SetDisplayMode(ais, 1, False)

    ais_wire = AIS_Shape(floor.polygon_wire)
    wire_drawer = ais_wire.Attributes()
    wire_line = Prs3d_LineAspect(green, Aspect_TOL_DOT, 2.0)
    wire_drawer.SetWireAspect(wire_line)
    context.Display(ais_wire, False)

# --- Grid cells: red wireframe boxes, one per floor level ---
for cell in grid.cells:
    box = BRepPrimAPI_MakeBox(
        gp_Pnt(*cell.min_pt),
        gp_Pnt(*cell.max_pt),
    ).Shape()

    ais_box = AIS_Shape(box)
    box_drawer = ais_box.Attributes()

    # Fully transparent fill so only the edges are visible
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

display.FitAll()
start_display()
