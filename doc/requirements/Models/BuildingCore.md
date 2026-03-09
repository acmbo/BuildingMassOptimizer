# Building Core — Requirements

_Based on Wang et al. (2019): "Subtractive Building Massing for Performance-Based Architectural
Design Exploration", Sustainability 11, 6965 — Section 2.2.4 Building Cores._

---

## 1. Concept and Role in the Algorithm

Building cores are vertical service zones within the building mass that serve as circulation,
evacuation, and structural support elements.  In the Wang et al. algorithm, core generation is an
**optional fourth step** executed after subtraction, and it is controlled by a single boolean
initialization parameter (`core_generation_enabled`).

The placement rule is derived from the Chinese firefighting evacuation regulation:

> The door-to-door distance from any point in a room to its closest stair/exit corridor must not
> exceed **22 m**.

Because the algorithm does not subdivide floor plans into rooms, this is simplified to:

> **Every face (edge) of the maximal-volume footprint polygon must be no more than 35 m from
> its closest building core.**

Once core positions are determined they are snapped to the **column grid**: the column-grid cell
whose center lies within half a column-grid span of the candidate core center is adopted as the
core's final position.

After cores are placed, all **subtractors must also align with the core boundaries** — the
subtractor face-snapping step is extended to treat core edges as additional snap targets.

---

## 2. Workflow (Wang et al. 2019)

```
1. [Optional] Check core_generation_enabled flag — skip entire section if False.

2. Extract the footprint polygon of the subtracted building mass
   (outer boundary of FloorData.polygon_wire at ground floor).

3. Determine number and position of cores so that every face of the
   footprint polygon satisfies: distance_to_nearest_core ≤ max_face_distance (default 35 m).

   Placement algorithm (centroid-first):
   a. Compute centroid of footprint polygon → candidate position.
   b. Snap candidate to nearest column-grid cell center
      (accept snap if distance ≤ 0.5 × min(span_x, span_y)).
   c. Add snapped position as BuildingCore.
   d. Measure distance from every footprint face to its nearest BuildingCore.
   e. If any face exceeds max_face_distance, place another core at the
      midpoint of the farthest face, snap it, and repeat from (d).

4. Store the resulting list[BuildingCore] on BuildingMass.cores.

5. Propagate cores to each FloorData.cores
   (all cores are active on every floor unless filtered by z-range).

6. Extend subtractor alignment: after ColumnGrid quarter-span snapping,
   also snap each subtractor face to the nearest core edge
   if the gap is within the boundary_snap_fraction threshold.
```

---

## 3. Data Model

### 3.1 `BuildingCore`  (`src/models/building_core.py`)

New dataclass representing one building core.

| Field | Type | Description |
|---|---|---|
| `center_x` | `float` | X coordinate of the snapped core center (model units) |
| `center_y` | `float` | Y coordinate of the snapped core center (model units) |
| `width` | `float` | Core footprint width in X — defaults to `column_grid.span_x` |
| `depth` | `float` | Core footprint depth in Y — defaults to `column_grid.span_y` |
| `column_ix` | `int` | Column-grid cell index along X (0-based) |
| `column_iy` | `int` | Column-grid cell index along Y (0-based) |

Derived properties:

| Property | Formula | Description |
|---|---|---|
| `x_min` | `center_x - width / 2` | Left edge in plan |
| `x_max` | `center_x + width / 2` | Right edge in plan |
| `y_min` | `center_y - depth / 2` | Front edge in plan |
| `y_max` | `center_y + depth / 2` | Back edge in plan |

The core extends the full height of the building (z = 0 to `total_height`).  No Z fields are
stored on `BuildingCore` itself — the consuming code reads height from `BuildingMass`.

Validation (in `__post_init__`):
- `width > 0`, `depth > 0`
- `column_ix >= 0`, `column_iy >= 0`

### 3.2 Changes to `FloorData`  (`src/models/floor_data.py`)

Add one new optional field:

```python
cores: list["BuildingCore"] = field(default_factory=list)
```

Interpretation: the list of building cores active on this floor.  For the initial implementation,
every floor carries the full `BuildingMass.cores` list (all cores span the full height).

### 3.3 Changes to `BuildingMass`  (`src/models/building_mass.py`)

Add one new optional field:

```python
cores: list["BuildingCore"] = field(default_factory=list)
```

The field is populated either by `find_building_cores()` or left empty (core generation disabled).

---

## 4. Core Engine  (`src/models/building_core_engine.py`)

Single public function:

```python
def find_building_cores(
    mass: BuildingMass,
    column_grid: ColumnGrid,
    max_face_distance: float = 35.0,
) -> list[BuildingCore]:
```

### 4.1 Input

| Parameter | Description |
|---|---|
| `mass` | Subtracted `BuildingMass` (ground floor polygon is used for face distance checks) |
| `column_grid` | `ColumnGrid` providing span sizes and grid line positions |
| `max_face_distance` | Maximum allowed distance from any footprint face to its nearest core (default 35 m) |

### 4.2 Footprint Extraction

- Use `mass.floors[0].polygon_wire` as the footprint shape.
- Traverse edges with `TopExp_Explorer(polygon_wire, TopAbs_EDGE)`.
- For each edge, compute its midpoint (average of the two end vertices).
- Represent each face as a `FaceSegment(midpoint_x, midpoint_y)` — distance checks use midpoints
  as the representative point per face.

### 4.3 Distance Metric

Distance from a face-midpoint `(fx, fy)` to a `BuildingCore` with center `(cx, cy)`:

```
d = sqrt((fx - cx)² + (fy - cy)²)
```

A face is **covered** if `d ≤ max_face_distance` for at least one core in the current list.

### 4.4 Snapping Candidate to Column Grid

Given a candidate XY point `(px, py)`:

1. Find the nearest column-grid cell center whose **entire footprint rectangle** lies
   inside solid material on every floor:
   - Cell centers lie at `(grid_lines_x[i] + span_x/2, grid_lines_y[j] + span_y/2)` for all
     `(i, j)` pairs (cells, not column lines).
   - Sort all cells by Euclidean distance to `(px, py)`.
   - Walk in distance order; for each cell validate 5 sample points of the core footprint
     (center + 4 corners at `cell_cx ± span_x/2`, `cell_cy ± span_y/2`) against the solid
     on **every** floor using `BRepClass3d_SolidClassifier`.  Accept the first cell where
     all 5 points classify as `TopAbs_IN` or `TopAbs_ON` on every floor.
2. Accept snap if the nearest valid cell is within `distance ≤ 0.5 × min(span_x, span_y)`.
3. If the nearest valid cell is beyond the threshold, prefer the raw candidate `(px, py)`
   provided its footprint also passes the 5-point check on every floor.
4. If neither succeeds, return `None` so the caller can supply a fallback.
5. Return `BuildingCore(center_x, center_y, width=span_x, depth=span_y, column_ix, column_iy)`.

**Rationale for footprint-area check:** checking only the center point allows the core
rectangle to clip a void when the center sits near a void boundary.  Checking all 4 corners
in addition to the center catches this case without requiring a full polygon intersection.

### 4.5 Placement Loop

```
# Build (solid, z_test) pairs for every floor — used to reject void positions
floor_tests = [(floor.solid, floor.elevation + floor.floor_height / 2)
               for floor in mass.floors]

cores = []

# Step 1: place first core at footprint centroid
centroid = compute_polygon_centroid(footprint_edges)
seed = snap_to_column_grid(centroid, column_grid, floor_tests)
if seed is None:
    # Centroid in void — try face midpoints sorted by centrality
    for fm in sorted(face_midpoints, by_distance_to=centroid):
        seed = snap_to_column_grid(fm, column_grid, floor_tests)
        if seed is not None:
            break
if seed is None:
    raise ValueError("no valid core position found")
cores.append(seed)

# Step 2: iteratively cover uncovered faces
while True:
    uncovered = [f for f in face_midpoints if not is_covered(f, cores, max_face_distance)]
    if not uncovered:
        break
    farthest = max(uncovered, key=lambda f: min_distance_to_cores(f, cores))
    core = snap_to_column_grid(farthest, column_grid, floor_tests)
    if core is None:
        # Fallback: place raw face midpoint (always on solid boundary)
        core = BuildingCore(center_x=farthest.x, center_y=farthest.y, ...)
    cores.append(core)

return cores
```

`snap_to_column_grid` validates the full footprint rectangle (center + 4 corners) on every
floor solid before accepting a position (see §4.4).

Guard: if the loop runs more than `len(face_midpoints)` iterations without convergence, raise:

```python
raise RuntimeError(
    f"Building core placement did not converge after {len(face_midpoints)} iterations. "
    f"{len(uncovered)} face(s) remain uncovered (max_face_distance={max_face_distance} m). "
    "This usually means the footprint is very elongated or max_face_distance is too small "
    "relative to the column-grid span."
)
```

`len(face_midpoints)` is the natural upper bound — no valid layout ever needs more cores than
faces — so no additional hardcoded constant is required.

---

## 5. Subtractor–Core Alignment (Extension to Existing Engine)

After the normal quarter-span snapping in `ColumnGrid.align_subtractor()`, each subtractor face
that is within `boundary_snap_fraction × span` of a core edge is additionally snapped to that
core edge.

This is an **extension** of the existing alignment step — it does not replace quarter-span
snapping, it supplements it.

Candidate implementation: add an optional `cores: list[BuildingCore]` parameter to
`ColumnGrid.align_subtractor()`.  When provided, after computing the quarter-span snapped
coordinates, apply a second pass that moves each snapped face to the nearest core edge if
closer than the snap threshold.

---

## 6. Relationship to Existing Components

```
BuildingMass (subtracted)
    │
    ├─ floors[0].polygon_wire ──► find_building_cores()
    │                                  │
    │                             ColumnGrid (snap candidates)
    │                                  │
    │                             list[BuildingCore]
    │                                  │
    ├─ cores ◄─────────────────────────┤
    │                                  │
    └─ floors[i].cores ◄───────────────┘  (same list propagated to each FloorData)

ColumnGrid.align_subtractor(sub, cores=cores)
    ├─ quarter-span snap  (existing)
    └─ core-edge snap     (new, if cores provided)
```

---

## 7. New Files

| File | Content |
|---|---|
| `src/models/building_core.py` | `BuildingCore` dataclass |
| `src/models/building_core_engine.py` | `find_building_cores()` |
| `test/models/test_building_core.py` | Unit tests (placement logic, snapping, edge cases) |
| `test/userInteraction/test_building_core.py` | Visual test: footprint + core boxes overlaid |

---

## 8. Parameters Summary

| Parameter | Location | Default | Description |
|---|---|---|---|
| `core_generation_enabled` | `IndividuumParams` (future) | `False` | Toggle the entire core step |
| `max_face_distance` | `find_building_cores()` | `35.0` m | Max face-to-nearest-core distance |
| `core_width` | `BuildingCore` / engine | `span_x` | Core footprint width (X) |
| `core_depth` | `BuildingCore` / engine | `span_y` | Core footprint depth (Y) |

---

## 9. Visual Test

`test/userInteraction/test_building_core.py`

Creates a subtracted building mass (reuse `test_individuum.py` setup) then:

1. Runs `find_building_cores()` with default 35 m threshold.
2. Displays:
   - Subtracted building mass (transparent white).
   - Footprint polygon wire (cyan).
   - Core footprint rectangles (solid blue, semi-transparent, full building height).
   - Face-midpoint markers (green dots) with a line to nearest core.
