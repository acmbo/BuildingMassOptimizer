"""
Visual inspection test: Subtractive Form Generation

Shows a 10x10 m, 5-floor building with three subtractors applied:
  1. Vertical subtractor — central courtyard (spans full height)
  2. Vertical subtractor — corner notch (open boundary, snapped through wall)
  3. Horizontal subtractor — stilts at ground level

Display legend:
  - Original building mass    → very faint grey (background reference)
  - Subtracted building mass  → transparent white solid + cyan floor wires
  - Subtractor boxes          → red wireframe (raw / no column-grid alignment)

Run manually (not collected by pytest):
    conda run -n pyoccEnv python test/userInteraction/test_subtraction.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from models import BuildingMass
from models.subtractor import Subtractor, SubtractorType, SubtractionConfig
from models.subtraction_engine import apply_subtractions

from OCC.Display.SimpleGui import init_display
from visualization.occ_scene import (
    add_building_mass,
    add_original_mass,
    add_subtractors,
    configure_diagnostic_background,
    configure_isometric_view,
    export_png,
)


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

configure_diagnostic_background(display)

context = display.Context

add_original_mass(context, original_mass)
add_building_mass(context, subtracted_mass, style="DIAGNOSTIC")
# Show subtractors in red wireframe (no column-grid alignment in this test)
raw_all = config.vertical_subtractors + config.horizontal_subtractors
add_subtractors(context, config=None, raw=raw_all)

configure_isometric_view(display)
start_display()
