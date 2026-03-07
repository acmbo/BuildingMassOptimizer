# MassCreator – Architecture & Technology Overview

## Stack

| Layer | Technology | Version |
|---|---|---|
| Language | Python | 3.13 |
| CAD kernel | OpenCASCADE (via pythonocc-core) | 7.9.3 |
| Viewer / GUI | pythonocc SimpleGui (Tkinter backend) | 7.9.3 |
| Test runner | pytest | 9.0.2 |
| Environment | Conda | – |

### Activating the environment
```bash
conda activate pyoccEnv
```

### Running tests
```bash
conda run -n pyoccEnv python -m pytest test/ -v
```

---

## Project structure

```
MassCreator/
├── src/
│   ├── floorgeneration.py        # Low-level OCC geometry primitives
│   ├── ARCHITECTURE.md           # This file
│   └── models/
│       ├── __init__.py           # Re-exports all public model classes
│       ├── floor_data.py         # FloorData dataclass
│       ├── building_mass.py      # BuildingMass dataclass + factory
│       ├── cell_mode.py          # CellMode enum
│       ├── grid_cell.py          # GridCell dataclass
│       ├── building_grid.py      # BuildingGrid dataclass + factory
│       ├── subtractor.py         # Subtractor, SubtractorType, SubtractionConfig
│       └── subtraction_engine.py # apply_subtractions(), extract_bottom_wire()
├── test/                         # mirrors src/ layout (see Testing Strategy)
│   ├── models/
│   │   ├── test_building_grid.py # unit tests for src/models/building_grid.py
│   │   └── test_subtraction.py   # unit tests for subtraction feature
│   └── userInteraction/          # special folder: visualisation-based tests
│       ├── test_floorgeneration.py  # visualisation: building mass only
│       ├── test_buildinggrid.py     # visualisation: building mass + grid
│       └── test_subtraction.py      # visualisation: original vs subtracted mass
└── doc/
    ├── requirements/
    │   ├── Models/
    │   │   ├── BuildingMass.md    # Data structure spec
    │   │   └── BuildingGrid.md    # Data structure spec
    │   └── SubtractiveFormGeneration.md  # Feature spec (Wang et al. 2019)
    └── paper/
```

---

## Testing strategy

### Red / green unit tests (`test/`)

Tests follow the **red / green** principle:
- **Red** — write a failing test that defines the expected behaviour before or alongside the implementation.
- **Green** — write the minimum code to make it pass.

Unit tests live in `test/` and **mirror the folder structure of `src/`**:

| Source file | Test file |
|---|---|
| `src/models/building_grid.py` | `test/models/test_building_grid.py` |
| `src/models/subtractor.py` + `subtraction_engine.py` | `test/models/test_subtraction.py` |
| `src/models/building_mass.py` | `test/models/test_building_mass.py` *(planned)* |
| `src/floorgeneration.py` | `test/test_floorgeneration.py` *(planned)* |

This 1-to-1 mapping makes it straightforward to find the test for any source file and vice versa.

Each test file is structured into focused test classes:
- **Green tests** — verify correct behaviour (valid inputs, expected outputs, derived values).
- **Red tests** — verify that invalid inputs raise the correct errors (`ValueError`, etc.).

Run all unit tests:
```bash
conda run -n pyoccEnv python -m pytest test/ -v
```

### Visualisation tests (`test/userInteraction/`)

`test/userInteraction/` is a **special, non-automated folder**. Scripts here
open an interactive 3D viewer and are run manually by the developer to
visually inspect geometry and rendering. They are **not collected by pytest**.

Each script in this folder corresponds to a feature or combination of features:

| Script | What it shows |
|---|---|
| `test_floorgeneration.py` | Building mass — transparent white solids, green floor wires |
| `test_buildinggrid.py` | Building mass + grid — adds red wireframe cell boxes |
| `test_subtraction.py` | Original mass (faint grey) vs subtracted mass (white) + red subtractor boxes |

Run a visualisation test directly:
```bash
conda run -n pyoccEnv python test/userInteraction/test_buildinggrid.py
conda run -n pyoccEnv python test/userInteraction/test_subtraction.py
```

---

## Module responsibilities

### `src/floorgeneration.py`
Pure OCC geometry primitives — no display code, no domain logic.

| Function | Returns | Purpose |
|---|---|---|
| `create_wire(points, z_offset)` | `TopoDS_Wire` | Closed polygon wire at a given Z elevation |
| `create_polygon(points)` | `TopoDS_Shape` (Face) | Planar face from a list of XY points |
| `translate_shape(shape, dz)` | `TopoDS_Shape` | Copy of shape moved by dz along Z |
| `extrude_face(face, height)` | `TopoDS_Shape` (Solid) | Extrusion of a face along +Z |

### `src/models/`
Domain model layer. All classes are Python `@dataclass`s. No display code.

| Class / Module | File | Role |
|---|---|---|
| `FloorData` | `floor_data.py` | Geometry + metadata for one floor (solid, wire, elevation, height) |
| `BuildingMass` | `building_mass.py` | Collection of floors; factory via `BuildingMass.create(polygon, floor_height, num_floors)` |
| `CellMode` | `cell_mode.py` | Enum: `FIXED_SIZE` or `CELL_COUNT` |
| `GridCell` | `grid_cell.py` | Single grid cell with `ix/iy/iz`, `min_pt`, `max_pt`, derived `center` |
| `BuildingGrid` | `building_grid.py` | 3D grid aligned to building AABB; factory via `BuildingGrid.create(mass, mode, ...)` |
| `SubtractorType` | `subtractor.py` | Enum: `VERTICAL` or `HORIZONTAL` |
| `Subtractor` | `subtractor.py` | Rectangular void defined by XY position, width/depth, and Z range; validated on creation |
| `SubtractionConfig` | `subtractor.py` | Holds all subtractors + constraint parameters (snap thresholds, plan size limits, boundary mode) |
| `apply_subtractions` | `subtraction_engine.py` | Applies a `SubtractionConfig` to a `BuildingMass` → returns new `BuildingMass` with cut floors |
| `extract_bottom_wire` | `subtraction_engine.py` | Extracts plan outline wire(s) from the bottom face of a cut floor solid |

---

## Data model overview

```
BuildingMass
├── polygon_points, floor_height, num_floors, total_height
└── floors: list[FloorData]
            ├── index, elevation, floor_height
            ├── solid          → TopoDS_Shape  (extruded / cut volume)
            └── polygon_wire   → TopoDS_Shape  (plan outline at elevation;
                                                may be a compound of wires after subtraction)

BuildingGrid
├── building_mass, cell_mode, cell_size
├── aabb_min, aabb_max
├── nx, ny, nz, cell_size_x, cell_size_y, cell_size_z, total_cells
└── cells: list[GridCell]
            ├── ix, iy, iz
            ├── min_pt, max_pt
            └── center  (derived)

SubtractionConfig
├── vertical_subtractors   : list[Subtractor]   (tall voids — courtyards, atriums, notches)
├── horizontal_subtractors : list[Subtractor]   (flat voids — stilts, cascades, partial floors)
├── vertical_snap_threshold     : float = 0.30
├── horizontal_max_height_ratio : float = 0.30
├── min_plan_size / max_plan_size : float
├── boundary_constraint_enabled : bool  = True
└── boundary_snap_fraction      : float = 0.10

Subtractor
├── x, y          – XY origin within building footprint
├── width, depth  – plan extent
├── z_bottom, z_top – absolute Z range
└── subtractor_type : SubtractorType  (VERTICAL | HORIZONTAL)
```

Key access helpers on `BuildingGrid`:
- `grid.get_cell(ix, iy, iz)` — direct indexed lookup
- `grid.cells_at_floor(iz)` — all cells for one floor level

---

## OpenCASCADE concepts used

### Topology (BRep)
OCC represents geometry as a **Boundary Representation (BRep)** tree:
```
Solid → Shell → Face → Wire → Edge → Vertex
```
All shapes are `TopoDS_Shape` objects.

### Key OCC modules in use

| Module | Purpose |
|---|---|
| `BRepBuilderAPI_MakePolygon` | Builds a closed wire from 3D points |
| `BRepBuilderAPI_MakeFace` | Converts a wire into a planar face |
| `BRepBuilderAPI_Transform` | Applies a `gp_Trsf` (translation, rotation, scale) |
| `BRepPrimAPI_MakePrism` | Extrudes a face along a `gp_Vec` → solid |
| `BRepPrimAPI_MakeBox` | Axis-aligned box from two corner points (grid cell visualisation + subtractor solids) |
| `Bnd_Box` + `brepbndlib` | Computes AABB of any shape or compound |
| `BRep_Builder` + `TopoDS_Compound` | Combines multiple shapes into one compound |
| `gp_Pnt / gp_Vec / gp_Trsf` | Geometric primitives |
| `AIS_Shape` | Interactive shape presentation in the viewer |
| `Prs3d_ShadingAspect` | Face fill colour and transparency |
| `Prs3d_LineAspect` | Edge colour, line type, and width |
| `Aspect_TOL_DOT / TOL_SOLID` | Line-type constants |
| `BRepAlgoAPI_Cut` | Boolean cut — subtract one solid from another |
| `BRepCheck_Analyzer` | Validate that a shape is geometrically sound after a cut |
| `TopExp_Explorer` | Traverse shape topology (Solid → Shell → Face → Wire → …) |

### AABB note
`brepbndlib` adds a small tolerance gap around solids. The actual AABB is
slightly larger than raw polygon coordinates. Grid cell counts are derived
from the real AABB, not from the input coordinates.

---

## Coordinate system

OCC uses a right-handed coordinate system:

- **X** → width
- **Y** → depth
- **Z** → height (up)

Floor polygons are defined in the XY plane (`z = 0`) and extruded along +Z.

---

## Notes for future development

### Inside/outside cell classification
The grid currently covers the full AABB. A next step is classifying each
`GridCell` as inside or outside the building polygon using
`BRepClass3d_SolidClassifier` — test the cell centre point against each
floor solid.

### Per-floor setbacks / offsets
Apply `BRepOffsetAPI_MakeOffset` on a floor wire before converting to a face,
or use `gp_Trsf.SetScale` to shrink/grow the polygon per floor.

### Boolean operations
`BRepAlgoAPI_Cut`, `BRepAlgoAPI_Fuse`, `BRepAlgoAPI_Common` — subtract
courtyards, punch openings, or merge masses. All operands must be solids.
Boolean subtraction is fully implemented via `apply_subtractions()` in
`subtraction_engine.py`.

### Exporting geometry
| Format | OCC API |
|---|---|
| STEP | `STEPControl_Writer` |
| BREP (native) | `BRepTools.Write` |
| STL (mesh) | `StlAPI_Writer` |

### Area / volume analysis
`GProp_GProps` + `BRepGProp.VolumeProperties` / `SurfaceProperties` — GFA
(Gross Floor Area) per floor.

### Switching GUI backend
`init_display()` auto-detects available backends (Tk, Qt5, Qt6, wx).
Install `PyQt5` or `PyQt6` for better rendering performance and HiDPI support.
