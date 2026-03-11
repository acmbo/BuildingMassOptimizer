"""
Visual inspection test: PyVista 3D scene rendering

Shows the same 10×10 m, 5-floor building with subtractors as
test_subtraction.py, rendered via PyVista instead of the OCC SimpleGui viewer.

Modes
-----
  --style DIAGNOSTIC    (default) Dark navy, transparent white mass, cyan edges,
                        red/orange subtractor wireframe boxes.
  --style ARCHITECTURAL White background, opaque light-grey building, ground
                        plane, no subtractor boxes.
  --save PATH           Export PNG to PATH instead of opening an interactive
                        window.  Useful for CI or quick inspection.

Run manually (not collected by pytest):
    conda run -n pyoccEnv python test/userInteraction/test_pyvista_scene.py
    conda run -n pyoccEnv python test/userInteraction/test_pyvista_scene.py --style ARCHITECTURAL
    conda run -n pyoccEnv python test/userInteraction/test_pyvista_scene.py --save /tmp/mass.png
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from models import BuildingMass
from models.subtractor import Subtractor, SubtractorType, SubtractionConfig
from models.subtraction_engine import apply_subtractions
from visualization.pyvista_scene import render_png


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(description="PyVista building mass test")
parser.add_argument("--style", choices=["DIAGNOSTIC", "ARCHITECTURAL"], default="DIAGNOSTIC")
parser.add_argument("--save", metavar="PATH", default=None,
                    help="Export PNG to this path instead of opening a window")
args = parser.parse_args()


# ---------------------------------------------------------------------------
# Building definition  (identical to test_subtraction.py)
# ---------------------------------------------------------------------------

polygon_points = [
    (0, 0, 0),
    (10, 0, 0),
    (10, 10, 0),
    (0, 10, 0),
]
floor_height = 3.0
num_floors = 5

original_mass = BuildingMass.create(polygon_points, floor_height, num_floors)

# ---------------------------------------------------------------------------
# Subtraction configuration
# ---------------------------------------------------------------------------

courtyard = Subtractor(
    x=3.0, y=3.0,
    width=4.0, depth=4.0,
    z_bottom=0.5,
    z_top=14.5,
    subtractor_type=SubtractorType.VERTICAL,
)

corner_notch = Subtractor(
    x=8.5, y=8.5,
    width=2.5, depth=2.5,
    z_bottom=0.2,
    z_top=14.8,
    subtractor_type=SubtractorType.VERTICAL,
)

stilts = Subtractor(
    x=1.5, y=0.0,
    width=7.0, depth=10.0,
    z_bottom=0.0,
    z_top=floor_height,
    subtractor_type=SubtractorType.HORIZONTAL,
)

config = SubtractionConfig(
    vertical_subtractors=[courtyard, corner_notch],
    horizontal_subtractors=[stilts],
    vertical_snap_threshold=0.30,
    horizontal_max_height_ratio=0.30,
    boundary_constraint_enabled=False,
    boundary_snap_fraction=0.10,
)

subtracted_mass = apply_subtractions(original_mass, config)

print(f"Style:      {args.style}")
print(f"Original:   {original_mass}")
print(f"Subtracted: {subtracted_mass}")

# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

raw_all = config.vertical_subtractors + config.horizontal_subtractors

if args.save:
    # Offscreen export
    render_png(
        subtracted_mass,
        args.save,
        style=args.style,
        config=config if args.style == "DIAGNOSTIC" else None,
        raw_subtractors=raw_all if args.style == "DIAGNOSTIC" else None,
        show_original=args.style == "DIAGNOSTIC",
        original_mass=original_mass,
        interactive=False,
    )
else:
    # Interactive window
    render_png(
        subtracted_mass,
        "",
        style=args.style,
        config=config if args.style == "DIAGNOSTIC" else None,
        raw_subtractors=raw_all if args.style == "DIAGNOSTIC" else None,
        show_original=args.style == "DIAGNOSTIC",
        original_mass=original_mass,
        interactive=True,
    )
