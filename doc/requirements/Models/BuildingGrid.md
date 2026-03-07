# BuildingGrid – Specification

## Purpose

A `BuildingGrid` subdivides the Axis-Aligned Bounding Box (AABB) of a
`BuildingMass` into a regular 3D grid of cells. Each cell spans:
- **X / Y** — uniform width/depth derived from the AABB
- **Z** — exactly one `floor_height` (cells are floor-aligned)

The grid is the foundation for spatial analysis: GFA calculations, point
classification, voxel-based operations, and visualisation.

---

## Input

| Parameter | Type | Description |
|---|---|---|
| `building_mass` | `BuildingMass` | Source geometry and floor metadata |
| `cell_mode` | `CellMode` | How cell size is determined (see below) |
| `cell_size` | `float` *(optional)* | Fixed cell length in X and Y (used when `cell_mode = FIXED_SIZE`) |
| `cell_count` | `int` *(optional)* | Target number of cells along the longest horizontal axis (used when `cell_mode = CELL_COUNT`) |

### Cell modes

```
CellMode.FIXED_SIZE   – user provides an absolute cell_size (e.g. 1.5 m)
CellMode.CELL_COUNT   – user provides a target count; cell_size is derived
```

For `CELL_COUNT`, the cell size is:
```
cell_size = max(aabb_width, aabb_depth) / cell_count
```
This keeps cells square and guarantees exactly `cell_count` divisions along
the longest axis. The shorter axis gets `ceil(extent / cell_size)` cells.

---

## AABB computation

The AABB is computed from the full `BuildingMass` (all floor solids combined):

```
xmin, ymin = min of all polygon x/y coordinates
xmax, ymax = max of all polygon x/y coordinates
zmin        = 0  (ground)
zmax        = building_mass.total_height
```

The AABB is stored on the grid so downstream code can reuse it without
recomputing.

---

## Derived values (stored on the model)

| Field | Formula |
|---|---|
| `aabb_min` | `(xmin, ymin, zmin)` |
| `aabb_max` | `(xmax, ymax, zmax)` |
| `cell_size_x` | `(xmax - xmin) / nx` — actual cell width after rounding |
| `cell_size_y` | `(ymax - ymin) / ny` — actual cell depth after rounding |
| `cell_size_z` | `floor_height` — same for every floor |
| `nx` | `ceil((xmax - xmin) / cell_size)` |
| `ny` | `ceil((ymax - ymin) / cell_size)` |
| `nz` | `num_floors` |
| `total_cells` | `nx × ny × nz` |

Cells are **exactly axis-aligned to the AABB**. The last column/row may be
slightly narrower than the rest if the AABB extent is not evenly divisible
by `cell_size` — this is expected and acceptable.

---

## `GridCell` (per cell)

```
GridCell
├── ix       : int    – column index (X axis, 0-based)
├── iy       : int    – row index    (Y axis, 0-based)
├── iz       : int    – floor index  (Z axis, 0-based, matches FloorData.index)
├── min_pt   : tuple[float, float, float]  – (xmin, ymin, zmin) corner
├── max_pt   : tuple[float, float, float]  – (xmax, ymax, zmax) corner
└── center   : tuple[float, float, float]  – cell centre point (derived)
```

`center` is derived in `__post_init__` and not stored as a separate init
parameter.

---

## `BuildingGrid` (top-level model)

```
BuildingGrid
├── building_mass  : BuildingMass
├── cell_mode      : CellMode
├── cell_size      : float              – resolved cell size (same in X and Y)
├── aabb_min       : tuple[float,float,float]
├── aabb_max       : tuple[float,float,float]
├── nx, ny, nz     : int                – grid dimensions
├── cell_size_x    : float              – actual X cell width
├── cell_size_y    : float              – actual Y cell depth
├── cell_size_z    : float              – = floor_height
├── total_cells    : int                – derived
└── cells          : list[GridCell]     – flat list, row-major order (ix, iy, iz)
```

### Factory classmethod

```python
BuildingGrid.create(building_mass, cell_mode, cell_size=None, cell_count=None)
```

Raises `ValueError` when:
- `cell_mode = FIXED_SIZE` and `cell_size` is not provided or <= 0
- `cell_mode = CELL_COUNT` and `cell_count` is not provided or < 1

---

## Cell ordering

Cells are stored in a **flat list** in row-major order:

```
for iz in range(nz):
    for iy in range(ny):
        for ix in range(nx):
            cells.append(...)
```

A helper method provides indexed access without manual arithmetic:

```python
grid.get_cell(ix, iy, iz) -> GridCell
```

---

## Access patterns

| Use case | Access |
|---|---|
| All cells on floor 2 | `[c for c in grid.cells if c.iz == 2]` |
| All cells in column (ix=0, iy=0) | `[c for c in grid.cells if c.ix == 0 and c.iy == 0]` |
| Cell at specific index | `grid.get_cell(ix, iy, iz)` |
| Grid dimensions | `grid.nx, grid.ny, grid.nz` |
| AABB | `grid.aabb_min, grid.aabb_max` |
| Total cell count | `grid.total_cells` |

---

## File layout

```
src/
├── floorgeneration.py          (existing – OCC geometry primitives)
└── models/
    ├── __init__.py             (re-exports all models)
    ├── floor_data.py           (existing)
    ├── building_mass.py        (existing)
    ├── cell_mode.py            (new – CellMode enum)
    ├── grid_cell.py            (new – GridCell dataclass)
    └── building_grid.py        (new – BuildingGrid dataclass + factory)

test/userInteraction/
    ├── test_floorgeneration.py (existing)
    └── test_buildinggrid.py    (new – visualisation with mass + grid)
```

---

## Notes for implementation

- Use `enum.Enum` for `CellMode` — keeps the public API explicit and avoids magic strings.
- `GridCell` is a plain dataclass with `eq=True` (default) so cells can be put in sets/dicts for lookup.
- The grid does **not** classify cells as inside/outside the building polygon — that is a separate analysis step (point-in-polygon / solid classification) to be added later.
- `BuildingGrid.create` should call `brepbndlib` on the compound of all floor solids to compute the AABB robustly, rather than doing it from raw polygon coordinates — this ensures correctness if the polygon is non-convex or if future offsets are applied.
