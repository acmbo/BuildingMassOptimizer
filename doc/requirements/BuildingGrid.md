# Building Grid – Requirements

---

## 1. Principle Summary

The `BuildingGrid` is a **3D axis-aligned bounding box (AABB) grid** overlaid on a
`BuildingMass`. It divides the building volume into a regular lattice of rectangular
cells for spatial analysis, performance simulation, and visualisation purposes.

The grid is **floor-aligned in Z**: each cell layer corresponds exactly to one floor of
the `BuildingMass`, so `cell_size_z == floor_height`. In the XY plane, cells are derived
from the OCC AABB of all floor solids and a user-selected sizing strategy.

---

## 2. Relationship to `BuildingMass`

```
BuildingMass
├── polygon_points: list[tuple[float,float,float]]   ← arbitrary polygon
└── floors: list[FloorData]
        └── solid    ← all solids are unioned into a compound for AABB

BuildingGrid  (derived from BuildingMass)
├── aabb_min, aabb_max       ← from OCC brepbndlib on all floor solids
├── nx, ny, nz               ← cell counts per axis
├── cell_size_x, cell_size_y ← actual cell dimensions (AABB evenly divided)
├── cell_size_z              ← == floor_height
└── cells: list[GridCell]    ← all cells in row-major order (iz, iy, ix)
```

The AABB is computed via `brepbndlib.Add(compound, bbox)` which adds a small OCC tolerance
gap around the solids. Cell sizes are then derived by dividing the AABB dimensions evenly
so that cells tile the box exactly.

---

## 3. Data Model

### 3.1 `CellMode`

Determines how the nominal cell size is resolved.

```
CellMode  (enum)
├── FIXED_SIZE   – user provides an absolute cell length in model units
└── CELL_COUNT   – user provides a target cell count along the longest horizontal axis;
                   cell size is derived so cells stay approximately square
```

### 3.2 `GridCell`

A single cell in the grid.

```
GridCell
├── ix      : int                        – column index along X (0-based)
├── iy      : int                        – row index along Y (0-based)
├── iz      : int                        – floor index along Z (0-based, matches FloorData.index)
├── min_pt  : tuple[float, float, float] – minimum corner (xmin, ymin, zmin)
├── max_pt  : tuple[float, float, float] – maximum corner (xmax, ymax, zmax)
└── center  : tuple[float, float, float] – cell centre point (derived in __post_init__)
```

### 3.3 `BuildingGrid`

```
BuildingGrid
├── building_mass  : BuildingMass
├── cell_mode      : CellMode
├── cell_size      : float          – nominal cell size (input for FIXED_SIZE; derived for CELL_COUNT)
├── aabb_min       : tuple[float, float, float]
├── aabb_max       : tuple[float, float, float]
├── nx             : int            – cell count along X
├── ny             : int            – cell count along Y
├── nz             : int            – cell count along Z (== num_floors)
├── cell_size_x    : float          – actual cell width  (AABB width  / nx)
├── cell_size_y    : float          – actual cell depth  (AABB depth  / ny)
├── cell_size_z    : float          – cell height        (== floor_height)
├── cells          : list[GridCell] – all cells, row-major order (iz, iy, ix)
└── total_cells    : int (derived)  – nx × ny × nz
```

---

## 4. Creation Modes

### FR-1  Two creation modes

| Mode | User provides | Grid derives |
|---|---|---|
| `FIXED_SIZE` | `cell_size` — absolute cell length | `nx`, `ny` via `ceil(aabb_dim / cell_size)` |
| `CELL_COUNT` | `cell_count` — target count along longest axis | `cell_size = max(width, depth) / cell_count`; then `nx`, `ny` |

In both modes, `cell_size_x` and `cell_size_y` are computed by dividing the AABB width and
depth by `nx` and `ny` respectively, so cells tile the bounding box exactly (they may differ
slightly from the nominal `cell_size`).

`nz` is always equal to `building_mass.num_floors`, and `cell_size_z` is always equal to
`building_mass.floor_height`. These are not user-configurable.

### FR-2  Factory signature

```python
BuildingGrid.create(
    building_mass : BuildingMass,
    cell_mode     : CellMode,
    cell_size     : float | None = None,   # required for FIXED_SIZE
    cell_count    : int   | None = None,   # required for CELL_COUNT
) -> BuildingGrid
```

### FR-3  Validation on construction

| Condition | Error |
|---|---|
| `FIXED_SIZE` with `cell_size` missing, zero, or negative | `ValueError` |
| `CELL_COUNT` with `cell_count` missing or < 1 | `ValueError` |
| Unknown `cell_mode` | `ValueError` |

---

## 5. Cell Layout

Cells are stored in **row-major order (iz, iy, ix)** — the outermost loop is Z (floor), then
Y (row), then X (column). This matches the generation loop:

```python
for iz in range(nz):
    for iy in range(ny):
        for ix in range(nx):
            min_pt = (xmin + ix * cell_size_x,
                      ymin + iy * cell_size_y,
                      zmin + iz * cell_size_z)
            max_pt = (xmin + (ix+1) * cell_size_x,
                      ymin + (iy+1) * cell_size_y,
                      zmin + (iz+1) * cell_size_z)
```

### Access helpers

```python
grid.get_cell(ix, iy, iz) -> GridCell          # direct index lookup
grid.cells_at_floor(iz)   -> list[GridCell]    # all cells on a single floor level
```

---

## 6. Quality Gates

Each gate maps to one or more automated unit tests in `test/models/test_building_grid.py`.

### QG-1  Cell mode and size are stored

```python
grid = BuildingGrid.create(mass, CellMode.FIXED_SIZE, cell_size=2.0)
assert grid.cell_mode == CellMode.FIXED_SIZE
assert abs(grid.cell_size - 2.0) < 1e-9
```

### QG-2  `nz` equals number of floors

```python
assert grid.nz == mass.num_floors
```

### QG-3  Total cell count

```python
assert grid.total_cells == grid.nx * grid.ny * grid.nz
assert len(grid.cells)  == grid.total_cells
```

### QG-4  Cells tile the AABB exactly

```python
assert abs(grid.nx * grid.cell_size_x - (aabb_max[0] - aabb_min[0])) < 1e-9
assert abs(grid.ny * grid.cell_size_y - (aabb_max[1] - aabb_min[1])) < 1e-9
```

### QG-5  `cell_size_z` equals `floor_height`

```python
assert abs(grid.cell_size_z - mass.floor_height) < 1e-9
```

### QG-6  Z range covers building height

```python
assert abs(grid.aabb_min[2] - 0.0)               < 1e-3
assert abs(grid.aabb_max[2] - mass.total_height)  < 1e-3
```

### QG-7  `CELL_COUNT` derives cell size from longest axis

```python
# mass is 10 × 6, longest = 10; cell_count=5 → cell_size = 10/5 = 2.0
grid = BuildingGrid.create(mass, CellMode.CELL_COUNT, cell_count=5)
assert abs(grid.cell_size - 2.0) < 1e-9
assert grid.nx == 5
```

### QG-8  First cell origin at AABB min; last cell corner at AABB max

```python
c_first = grid.get_cell(0, 0, 0)
assert abs(c_first.min_pt[0] - grid.aabb_min[0]) < 1e-5
c_last  = grid.get_cell(grid.nx-1, grid.ny-1, grid.nz-1)
assert abs(c_last.max_pt[0]  - grid.aabb_max[0]) < 1e-5
```

### QG-9  Adjacent cells share a face

```python
c0 = grid.get_cell(0, 0, 0)
c1 = grid.get_cell(1, 0, 0)
assert abs(c0.max_pt[0] - c1.min_pt[0]) < 1e-5
```

### QG-10  `cells_at_floor` returns `nx × ny` cells with correct `iz`

```python
floor_cells = grid.cells_at_floor(0)
assert len(floor_cells) == grid.nx * grid.ny
assert all(c.iz == 0 for c in floor_cells)
```

### QG-11  Cell centre is the midpoint of `min_pt` / `max_pt`

```python
cell = grid.get_cell(0, 0, 0)
assert abs(cell.center[0] - (cell.min_pt[0] + cell.max_pt[0]) / 2) < 1e-9
```

### QG-12  Invalid input raises `ValueError`

```python
with pytest.raises(ValueError):
    BuildingGrid.create(mass, CellMode.FIXED_SIZE, cell_size=0)

with pytest.raises(ValueError):
    BuildingGrid.create(mass, CellMode.CELL_COUNT, cell_count=0)
```

---

## 7. OCC APIs Used

| Operation | OCC API |
|---|---|
| Build compound of all floor solids | `BRep_Builder.MakeCompound` + `BRep_Builder.Add` |
| Compute AABB of compound | `brepbndlib.Add(compound, bbox)` then `bbox.Get()` |

Note: `brepbndlib` adds a small tolerance gap around each solid. Cell sizes are derived from
the padded AABB, not the raw polygon extents. This is intentional — it ensures the grid
fully encloses all geometry including OCC face normals at boundaries.

---

## 8. File Layout

```
src/
└── models/
    ├── cell_mode.py        – CellMode enum: FIXED_SIZE | CELL_COUNT
    ├── grid_cell.py        – GridCell dataclass (ix, iy, iz, min_pt, max_pt, center)
    └── building_grid.py    – BuildingGrid dataclass + factory + access helpers

test/
└── models/
    └── test_building_grid.py   – unit tests covering QG-1 through QG-12

test/userInteraction/
    └── test_buildinggrid.py    – visual inspection: building mass with grid cells
                                  drawn in red at each floor level
```

---

## 9. Relationship to `ColumnGrid`

| | `BuildingGrid` | `ColumnGrid` |
|---|---|---|
| Purpose | 3-D voxel grid for spatial analysis | 2-D structural modulus for subtractor alignment |
| Extent | OCC AABB of building solids (with tolerance gap) | XY bounding box of raw polygon points |
| Z dimension | Yes — one cell layer per floor | No — plan-only (2-D), uniform across all floors |
| Cell/span mode | `FIXED_SIZE` or `CELL_COUNT` (single size for both axes) | `FIXED_SPAN` or `SPAN_COUNT` (independent X and Y spans) |
| Outputs | `GridCell` objects with `min_pt`, `max_pt`, `center` | Grid line coordinate lists only |
| Snap operation | Not supported | `snap_to_grid()`, `align_subtractor()` |

The two grids are **independent** and may coexist on the same `BuildingMass`.

---

## 10. Open Questions / Future Extensions

| Topic | Note |
|---|---|
| **Inside/outside classification** | Cells could be tagged as inside, outside, or boundary relative to the building polygon for per-cell GFA computation. Requires a point-in-polygon test against `polygon_points`. |
| **Post-subtraction update** | After `apply_subtractions()`, the floor solids change shape. `BuildingGrid` currently holds the original AABB and does not update. A `rebuild()` method or lazy re-creation from the modified mass would be needed. |
| **Non-square cells** | `CELL_COUNT` derives a single `cell_size` from the longest axis, keeping cells approximately square. An independent `cell_count_x` / `cell_count_y` option could allow explicitly non-square cells. |
| **Performance analysis** | Each `GridCell.center` is a natural sample point for daylight, solar, or CFD analysis. A future step would classify each cell (e.g. exterior-facing, interior, void) and attach analysis results. |
