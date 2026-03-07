import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from models import BuildingMass
from OCC.Core.AIS import AIS_Shape
from OCC.Core.Aspect import Aspect_TOL_DOT
from OCC.Core.Prs3d import Prs3d_LineAspect, Prs3d_ShadingAspect
from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB, Quantity_NOC_WHITE
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

# --- Generate building mass ---
mass = BuildingMass.create(polygon_points, floor_height, num_floors)

print(mass)
print(f"  Polygon points : {mass.polygon_points}")
print(f"  Floor height   : {mass.floor_height}")
print(f"  Total height   : {mass.total_height}")

# --- Visualize ---
display, start_display, add_menu, add_function_to_menu = init_display()

# Dark dark blue background (set_bg_gradient_color works for Tk backend;
# both stops identical = solid colour, values are 0-255 integers)
dark_blue_rgb = [5, 5, 30]
display.set_bg_gradient_color(dark_blue_rgb, dark_blue_rgb)

context = display.Context
white = Quantity_Color(Quantity_NOC_WHITE)
green = Quantity_Color(0.2, 1.0, 0.45, Quantity_TOC_RGB)

for floor in mass.floors:
    # --- Solid: very transparent white fill, dotted white edges ---
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
    context.SetDisplayMode(ais, 1, False)   # 1 = shading

    # --- Floor polygon wire: green ---
    ais_wire = AIS_Shape(floor.polygon_wire)
    wire_drawer = ais_wire.Attributes()
    wire_line = Prs3d_LineAspect(green, Aspect_TOL_DOT, 2.0)
    wire_drawer.SetWireAspect(wire_line)
    context.Display(ais_wire, False)

display.FitAll()
start_display()
