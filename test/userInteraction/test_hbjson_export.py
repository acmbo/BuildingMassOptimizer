"""
Manual test: export a building mass to HBJson and print a summary.

Run:
    conda run -n pyoccEnv python test/userInteraction/test_hbjson_export.py

Exports to /tmp/test_building.hbjson for manual inspection in a text editor
or import into Grasshopper / Ladybug Tools.
"""
import sys
import os
import json
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from models import BuildingMass
from models.hbjson_exporter import export_to_hbjson

OUTPUT_PATH = "/tmp/test_building.hbjson"

# ---------------------------------------------------------------------------
# Build a 20 × 30 m, 5-floor mass at 3.5 m per floor
# ---------------------------------------------------------------------------
POLYGON = [(0, 0, 0), (20, 0, 0), (20, 30, 0), (0, 30, 0)]
FLOOR_HEIGHT = 3.5
NUM_FLOORS = 5

mass = BuildingMass.create(POLYGON, FLOOR_HEIGHT, NUM_FLOORS)

model = export_to_hbjson(
    mass,
    OUTPUT_PATH,
    identifier="TestBuilding",
    display_name="20×30 m, 5 floors",
)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\nHBJson export summary")
print(f"  Output:      {OUTPUT_PATH}")
print(f"  Model id:    {model['identifier']}")
print(f"  Total rooms: {len(model['rooms'])}")
print()

for room in model["rooms"]:
    face_types = Counter(f["face_type"] for f in room["faces"])
    bc_types = Counter(f["boundary_condition"]["type"] for f in room["faces"])
    print(
        f"  Room {room['identifier']}"
        f"  faces={len(room['faces'])}"
        f"  types={dict(face_types)}"
        f"  bc={dict(bc_types)}"
    )

total_faces = sum(len(r["faces"]) for r in model["rooms"])
all_bcs = Counter(
    f["boundary_condition"]["type"]
    for r in model["rooms"]
    for f in r["faces"]
)
print(f"\n  Total faces: {total_faces}")
print(f"  BC summary:  {dict(all_bcs)}")
print(f"\nFile written to {OUTPUT_PATH}\n")
