# ColumnGrid – Requirements

## Source

Wang et al. (2019), "Subtractive Building Massing for Performance-Based Architectural Design
Exploration: A Case Study of Daylighting Optimization", *Sustainability* 11, 6965.
Section 2.2.3 (Alignment) and Section 2.4.2 (Initialization Parameters).

---

## 1. Concept Summary

In the paper's algorithm, the **column grid** is the structural modular grid that spans the
building floor plan. It serves two roles:

1. **Dimensional modulus for the maximal volume** — the paper defines the building footprint
   from the grid: `nx_spans × span_x` wide, `ny_spans × span_y` deep.

2. **Alignment reference for subtractors** — all subtractor faces (the walls of the voids)
   are snapped to the nearest `n/4` position between two adjacent column lines (where `n` is
   an integer ≥ 0). This ensures subtracted faces align with the structural grid, producing
   architecturally coherent floor plans.

**Adaptation for this codebase:** `BuildingMass` takes an arbitrary polygon as input — it
is not constrained to a rectangle. The column grid therefore cannot *define* the footprint
as in the paper. Instead it is *fitted to* the existing polygon's bounding box, mirroring
the pattern already established by `BuildingGrid`. The grid's role is then purely the
alignment reference (role 2 above). Subtractors placed on an irregular footprint are still
constrained by the existing boundary mechanism in `SubtractionConfig`.

**The column grid is building-wide, not per-floor.** One grid instance covers the entire
building. Its X/Y lines are identical at every floor level. This models the physical reality:
structural columns run continuously from ground to roof — a column at position `(gx, gy)` on
floor 1 must also exist at the same `(gx, gy)` on floor 5. A per-floor grid would break this
alignment guarantee.

---

## 2. Relationship to Existing Models

```
BuildingMass
├── polygon_points: list[tuple[float,float,float]]   ← arbitrary polygon; Z ignored
└── floors: list[FloorData]
        └── solid, polygon_wire    ← geometry to be cut

ColumnGrid  (new)
├── span_x, span_y                 ← column spacing in X and Y
├── nx_spans, ny_spans             ← number of spans derived from polygon bbox + span
├── origin_x, origin_y            ← derived from polygon bbox min corner (NOT user input)
├── grid_lines_x: list[float]     ← absolute X positions of all column lines
└── grid_lines_y: list[float]     ← absolute Y positions of all column lines

SubtractionConfig  (existing)
└── (future) column_grid: ColumnGrid  ← used to snap subtractor faces during alignment
```

### ColumnGrid vs BuildingGrid

| | `BuildingGrid` | `ColumnGrid` |
|---|---|---|
| Purpose | 3-D voxel grid for spatial analysis | 2-D structural modulus for subtractor alignment |
| Extent | AABB of building solids (OCC brepbndlib) | XY bounding box of polygon points |
| Z dimension | Yes — floor-aligned cells in all three axes | No — plan-only (2-D), uniform across all floors |
| Floor scope | One layer of cells per floor | One grid for the entire building |
| Cell/span mode | FIXED_SIZE or CELL_COUNT (one size, both axes) | FIXED_SPAN or SPAN_COUNT (independent X and Y) |
| Outputs | `GridCell` objects (ix/iy/iz, min_pt, max_pt) | Grid line coordinate lists only |
| Snap operation | Not supported | `snap_to_grid()`, `align_subtractor()` |

The two grids are **independent** and may coexist.

### Why polygon bbox, not OCC AABB

`BuildingGrid` derives its bounding box from OCC `brepbndlib`, which adds a small tolerance
gap around solids. For `ColumnGrid`, the origin and span positions should align cleanly to
the polygon corners, so the bounding box is computed directly from `polygon_points`:

```
poly_xmin = min(p[0] for p in polygon_points)
poly_xmax = max(p[0] for p in polygon_points)
poly_ymin = min(p[1] for p in polygon_points)
poly_ymax = max(p[1] for p in polygon_points)
```

The grid origin is `(poly_xmin, poly_ymin)`. The grid covers at least the full polygon
extent, and may extend slightly beyond it when the polygon width/depth is not an exact
multiple of the span.

---

## 3. Functional Requirements

### FR-1  Two creation modes

`ColumnGrid` shall support two modes, mirroring `BuildingGrid`'s pattern:

| Mode | User provides | Grid derives |
|---|---|---|
| `FIXED_SPAN` | `span_x`, `span_y` | `nx_spans`, `ny_spans` from polygon bbox |
| `SPAN_COUNT` | `nx_spans`, `ny_spans` | `span_x`, `span_y` from polygon bbox |

In both modes, `origin_x` and `origin_y` are always derived from the polygon bbox and are
never supplied directly by the user.

### FR-2  Inputs and derived fields

**User inputs (via factory):**

| Parameter | Type | Required for |
|---|---|---|
| `building_mass` | `BuildingMass` | Both modes — provides the polygon |
| `mode` | `SpanMode` (enum) | Both modes |
| `span_x` | `float > 0` | FIXED_SPAN |
| `span_y` | `float > 0` | FIXED_SPAN |
| `nx_spans` | `int ≥ 1` | SPAN_COUNT |
| `ny_spans` | `int ≥ 1` | SPAN_COUNT |

**Derived fields (computed in factory, stored on instance):**

| Field | How derived |
|---|---|
| `origin_x` | `min(p[0] for p in polygon_points)` |
| `origin_y` | `min(p[1] for p in polygon_points)` |
| `nx_spans` | `ceil(bbox_width / span_x)` *(FIXED_SPAN)* |
| `ny_spans` | `ceil(bbox_depth / span_y)` *(FIXED_SPAN)* |
| `span_x` | `bbox_width / nx_spans` *(SPAN_COUNT)* |
| `span_y` | `bbox_depth / ny_spans` *(SPAN_COUNT)* |
| `grid_lines_x` | `[origin_x + i * span_x for i in range(nx_spans + 1)]` |
| `grid_lines_y` | `[origin_y + j * span_y for j in range(ny_spans + 1)]` |

In FIXED_SPAN mode, `span_x/span_y` are the user-supplied values; `nx_spans/ny_spans` are
rounded up with `ceil`, so the grid always fully covers the polygon bbox. As a consequence,
the rightmost / top column line may lie beyond the polygon boundary.

In SPAN_COUNT mode, `nx_spans/ny_spans` are the user-supplied values; `span_x/span_y` are
derived by dividing the bbox dimensions evenly (same approach as `BuildingGrid.cell_size_x/y`).

### FR-3  Grid line enumeration

The grid shall expose the column line positions as ordered lists:

```
grid_lines_x = [origin_x + i * span_x  for i in range(nx_spans + 1)]
grid_lines_y = [origin_y + j * span_y  for j in range(ny_spans + 1)]
```

There are `nx_spans + 1` lines in X and `ny_spans + 1` lines in Y. The first line coincides
with the polygon bbox min corner; the last line is at or beyond the polygon bbox max corner.

### FR-4  Total coverage dimensions

The grid shall expose how much plan area it covers:

```
total_width  = nx_spans * span_x   # >= bbox_width  (may be slightly larger in FIXED_SPAN)
total_depth  = ny_spans * span_y   # >= bbox_depth
```

### FR-5  Quarter-span snap positions

For each axis the grid shall expose all valid snap positions at quarter-span intervals:

```
snap_positions_x = [origin_x + i * span_x / 4  for i in range(nx_spans * 4 + 1)]
snap_positions_y = [origin_y + j * span_y / 4  for j in range(ny_spans * 4 + 1)]
```

These are the positions to which subtractor faces are aligned (FR-6).

### FR-6  Subtractor face snapping

Given a coordinate value `v`, the grid shall return the nearest quarter-span position:

```
snap_to_grid(v, axis='x' | 'y')  ->  float
```

The returned value is the element from the relevant snap positions list closest to `v`.

Before a subtractor is applied, each of its four plan-side face coordinates shall be snapped:

| Subtractor field | Axis |
|---|---|
| `x` (left face) | X |
| `x + width` (right face) | X |
| `y` (front face) | Y |
| `y + depth` (back face) | Y |

The snapped `width = snapped(x + width) − snapped(x)`, and similarly for `depth`.
If the snapped width or depth is ≤ 0, the subtractor is **deactivated** (returns `None`).

This operation does not require the polygon to be rectangular — the snap grid tiles the
bounding box, and the existing boundary constraint in `SubtractionConfig` handles which
parts of the footprint are available for subtraction.

### FR-7  Two-subtractor proximity alignment

When two subtractor faces on the same axis are closer than `0.5 × span` apart, those
two faces shall be aligned to a shared quarter-span position. This prevents narrow unusable
gaps between adjacent voids.

- **Separated subtractors**: gap between facing sides < `0.5 × span` → both faces move to
  their shared nearest quarter-span position.
- **Overlapping subtractors**: overlapping faces are unified the same way.
- **Boundary proximity**: a subtractor face within `0.5 × span` of the polygon bbox boundary
  is handled by the existing boundary constraint in `SubtractionConfig`.

### FR-9  Single grid for the whole building (floor-independent)

A `ColumnGrid` is created once per `BuildingMass` and applies identically to every floor.
It has **no Z dimension and no per-floor variant**. The same `grid_lines_x` and
`grid_lines_y` are used when aligning subtractors on floor 0, floor 3, or any other floor.

This models the structural constraint that columns are continuous vertical elements: a column
at plan position `(gx, gy)` must occupy that same XY position on every floor from ground to
roof. Making the grid building-wide enforces this automatically — there is no mechanism to
produce a different alignment on different floors.

Consequences:
- `ColumnGrid` stores no reference to individual floors and no floor index.
- `align_subtractor(sub)` ignores `sub.z_bottom` and `sub.z_top` — Z is irrelevant to plan
  alignment.
- When `apply_subtractions()` loops over floors, it calls the same `align_subtractor()` for
  every floor without modification.

### FR-8  Validation on construction

The factory shall raise `ValueError` for:

| Condition | Message |
|---|---|
| FIXED_SPAN: `span_x <= 0` | "span_x must be positive" |
| FIXED_SPAN: `span_y <= 0` | "span_y must be positive" |
| SPAN_COUNT: `nx_spans < 1` | "nx_spans must be at least 1" |
| SPAN_COUNT: `ny_spans < 1` | "ny_spans must be at least 1" |
| `building_mass` has no polygon points | "building_mass must have polygon_points" |

---

## 4. Quality Gates

Each quality gate maps directly to one or more automated unit tests.

### QG-1  Origin is derived from polygon, not user input

```python
polygon = [(2.0, 3.0, 0), (12.0, 3.0, 0), (12.0, 11.0, 0), (2.0, 11.0, 0)]
mass = BuildingMass.create(polygon, floor_height=3.0, num_floors=4)
grid = ColumnGrid.create(mass, SpanMode.FIXED_SPAN, span_x=4.0, span_y=4.0)

assert abs(grid.origin_x - 2.0) < 1e-9
assert abs(grid.origin_y - 3.0) < 1e-9
```

### QG-2  Grid fully covers polygon bounding box

```python
bbox_width  = max(p[0] for p in polygon) - min(p[0] for p in polygon)  # 10.0
bbox_depth  = max(p[1] for p in polygon) - min(p[1] for p in polygon)  # 8.0

assert grid.total_width  >= bbox_width  - 1e-9
assert grid.total_depth  >= bbox_depth  - 1e-9
```

### QG-3  Grid line count

```python
assert len(grid.grid_lines_x) == grid.nx_spans + 1
assert len(grid.grid_lines_y) == grid.ny_spans + 1
```

### QG-4  Grid line spacing is uniform

```python
for i in range(len(grid.grid_lines_x) - 1):
    assert abs(grid.grid_lines_x[i+1] - grid.grid_lines_x[i] - grid.span_x) < 1e-9

for j in range(len(grid.grid_lines_y) - 1):
    assert abs(grid.grid_lines_y[j+1] - grid.grid_lines_y[j] - grid.span_y) < 1e-9
```

### QG-5  SPAN_COUNT mode derives span from polygon bbox

```python
grid = ColumnGrid.create(mass, SpanMode.SPAN_COUNT, nx_spans=2, ny_spans=2)
# bbox_width = 10.0, nx_spans = 2  →  span_x = 5.0
assert abs(grid.span_x - 5.0) < 1e-9
assert abs(grid.span_y - 4.0) < 1e-9
```

### QG-6  Quarter-span snap count

```python
assert len(grid.snap_positions_x) == grid.nx_spans * 4 + 1
assert len(grid.snap_positions_y) == grid.ny_spans * 4 + 1
```

### QG-7  Snap result is always a member of snap positions

For any input `v`, `snap_to_grid(v, axis)` returns a value within the snap positions list:

```python
result = grid.snap_to_grid(5.3, axis='x')
assert any(abs(result - p) < 1e-9 for p in grid.snap_positions_x)
```

### QG-8  Snap returns the nearest position

```python
# With span_x=4.0, quarter positions at origin_x + 0, 1, 2, 3, 4, ...
# (origin_x = 2.0) → positions at 2, 3, 4, 5, 6, ...
assert abs(grid.snap_to_grid(4.9, axis='x') - 5.0) < 1e-9   # closer to 5 than to 4
assert abs(grid.snap_to_grid(3.1, axis='x') - 3.0) < 1e-9   # closer to 3 than to 4
```

### QG-9  Subtractor alignment lands on grid positions

After `align_subtractor`, all four face coordinates lie on quarter-span positions:

```python
snapped = grid.align_subtractor(sub)
assert any(abs(snapped.x           - p) < 1e-9 for p in grid.snap_positions_x)
assert any(abs(snapped.x + snapped.width  - p) < 1e-9 for p in grid.snap_positions_x)
assert any(abs(snapped.y           - p) < 1e-9 for p in grid.snap_positions_y)
assert any(abs(snapped.y + snapped.depth  - p) < 1e-9 for p in grid.snap_positions_y)
```

### QG-10  Zero or negative snapped dimension deactivates subtractor

```python
result = grid.align_subtractor(sub_with_tiny_width)
assert result is None
```

### QG-11  Non-rectangular polygon: origin from polygon, not AABB with tolerance

The OCC AABB includes a small tolerance gap. `ColumnGrid` must derive its origin from the
raw polygon points, not from OCC:

```python
poly_xmin = min(p[0] for p in polygon)
assert abs(grid.origin_x - poly_xmin) < 1e-9   # exact, no OCC tolerance offset
```

### QG-13  Grid is identical across all floors

The grid lines do not change with floor index. The same `grid_lines_x` and `grid_lines_y`
must apply for floor 0, floor N/2, and floor N-1:

```python
mass = BuildingMass.create(polygon, floor_height=3.0, num_floors=8)
grid = ColumnGrid.create(mass, SpanMode.FIXED_SPAN, span_x=4.0, span_y=4.0)

# Grid has no per-floor state — lines are the same regardless of which floor is queried
for floor in mass.floors:
    snapped = grid.align_subtractor(sub)
    # snapped result is identical for every floor (Z is not involved in plan alignment)
    assert abs(snapped.x - expected_x) < 1e-9

# ColumnGrid stores no floor list or floor count
assert not hasattr(grid, 'floors')
assert not hasattr(grid, 'nz')
```

### QG-12  Invalid construction raises ValueError

```python
with pytest.raises(ValueError):
    ColumnGrid.create(mass, SpanMode.FIXED_SPAN, span_x=0.0, span_y=4.0)

with pytest.raises(ValueError):
    ColumnGrid.create(mass, SpanMode.SPAN_COUNT, nx_spans=0, ny_spans=3)
```

---

## 5. File Layout

```
src/
└── models/
    ├── span_mode.py            (new) – SpanMode enum: FIXED_SPAN | SPAN_COUNT
    └── column_grid.py          (new) – ColumnGrid dataclass + factory
                                        snap_to_grid(), align_subtractor()

test/
└── models/
    └── test_column_grid.py     (new) – unit tests covering QG-1 through QG-13

test/userInteraction/
    └── test_column_grid.py     (new, optional) – visual: polygon footprint with
                                                   column grid lines overlaid,
                                                   before/after subtractor snapping
```

---

## 6. Integration with SubtractionConfig

`ColumnGrid` is optional. When present alongside a `SubtractionConfig`, the alignment step
(FR-6, FR-7) runs as a pre-processing pass **before** the existing constraint checks.

The existing `min_plan_size` / `max_plan_size` in `SubtractionConfig` are expressed in
**column-grid spans** (per the paper). When a `ColumnGrid` is provided, these limits convert
to model units as:

```
min_plan_size_x_m = min_plan_size * span_x
max_plan_size_x_m = max_plan_size * span_x
min_plan_size_y_m = min_plan_size * span_y
max_plan_size_y_m = max_plan_size * span_y
```

The boundary constraint in `SubtractionConfig` remains responsible for keeping subtractors
within the buildable area — `ColumnGrid` only governs alignment, not placement validity.

---

## 7. Design Decision: New `ColumnGrid` vs Reusing `BuildingGrid`

### Option A — Implement a separate `ColumnGrid`  *(recommended)*

**Pros:**
- **Correct semantic model.** `BuildingGrid` is a 3-D voxel grid for spatial analysis.
  `ColumnGrid` is a 2-D structural modulus for alignment. They answer different questions
  and should not share a type.
- **Floor-agnostic by design.** `ColumnGrid` has no Z dimension and no floor list.
  `BuildingGrid` always has `nz` layers (one per floor). Forcing it to act as a 2-D grid
  would require using `nz=1` as a workaround — semantically wrong and fragile.
- **Independent span axes.** `ColumnGrid` needs `span_x` and `span_y` as separate values
  (column grids commonly use different spans per axis). `BuildingGrid` has a single
  `cell_size` for both X and Y; extending it would change existing behaviour.
- **Polygon bbox, not OCC AABB.** `ColumnGrid` derives its origin from raw `polygon_points`
  (no tolerance gap). `BuildingGrid` uses `brepbndlib` which adds an OCC tolerance offset.
  Changing `BuildingGrid` to use polygon points would break its existing tests and design.
- **Snap operations are domain-specific.** `snap_to_grid()` and `align_subtractor()` belong
  to the column-grid concept. Adding them to `BuildingGrid` would make that class do two
  unrelated jobs.
- **Isolation.** Future changes to `BuildingGrid` for analysis purposes (e.g. inside/outside
  classification, GFA per cell) cannot accidentally affect subtractor alignment.

**Cons:**
- One additional small file (`span_mode.py`, `column_grid.py`).
- Some conceptual overlap — both grids derive from the building's XY extent.

---

### Option B — Reuse `BuildingGrid`

**Pros:**
- No new file; reuses existing, tested code.
- `BuildingGrid.create()` factory pattern already exists.

**Cons:**
- Would require adding `snap_to_grid()` and `align_subtractor()` to `BuildingGrid`, mixing
  analysis and alignment concerns in one class.
- `cell_size` is a single value for X and Y — supporting `span_x ≠ span_y` would require
  a breaking API change.
- `BuildingGrid` always creates `GridCell` objects for every floor — wasted allocations for
  column alignment, which only needs line coordinates.
- The OCC-tolerance AABB origin would cause the column lines to be offset from the polygon
  corners by a small but non-zero amount, making snap positions misalign with actual geometry.
- `nz` (floor count) would be meaningless for a 2-D column grid; using `nz=1` is a hack.
- The class name `BuildingGrid` would no longer accurately describe structural column layout.

---

**Conclusion:** Implement `ColumnGrid` as a separate, lightweight 2-D model. The differences
(dimensionality, origin derivation, span axes, snap operations) are fundamental, not cosmetic.
Reusing `BuildingGrid` would require compromises that degrade both classes.

---

## 9. Open Questions / Future Extensions

| Topic | Note |
|---|---|
| **Non-axis-aligned polygons** | If the polygon is rotated relative to XY axes, a rotated column grid would be needed. The current spec assumes the grid is always axis-aligned, matching the project's coordinate convention. |
| **Per-wing grids** | The paper's second case study uses an L-shaped footprint split into two wings, each with its own grid. This would require multiple `ColumnGrid` instances, one per wing. |
| **Z-direction module** | The paper uses `floor_height` as the vertical modulus. A future extension could expose floor-level snap positions in Z for horizontal subtractor alignment. |
| **Structural column visualisation** | Column intersections (`grid_lines_x[i]`, `grid_lines_y[j]`) could be rendered as point markers in the viewer, overlaid on the polygon footprint. |
