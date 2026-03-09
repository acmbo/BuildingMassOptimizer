# Hallway Exploration — Requirements

_Hybrid "Rectilinear Skeleton" approach combining Medial Axis Skeletonization with
Grid-Based Partitioning to generate constructible hallway layouts within a building floor polygon._

---

## 1. Algorithm Overview

The algorithm generates circulation layouts by:

1. Computing the natural spine of a floor polygon via a **Medial Axis Transform**.
2. Simplifying and **orthogonalizing** that skeleton into straight, axis-aligned segments.
3. **Snapping** those segments to the structural column grid.
4. **Buffering** the snapped centrelines to a configured hallway width.
5. **Subtracting** the hallway polygon from the floor to produce room zones.

This mimics the human design process: sketch the flow (skeleton), then draw straight walls (grid).

### 1.1 Key Terms

| Term | Meaning |
|---|---|
| **Floor polygon** | The 2-D horizontal boundary of one building floor (XY plane, Z = elevation) |
| **Medial axis** | Set of all interior points equidistant from two or more boundary edges; forms the "spine" |
| **Skeleton graph** | Medial axis represented as a planar graph (nodes + edges) after pruning |
| **Orthogonalization** | Process of snapping skeleton edges to 0° / 90° only |
| **Column grid** | Regular lattice of structural axes used to snap hallway positions |
| **Hallway polygon** | 2-D area representing the hallway after buffering the centreline |
| **Room zone** | Remainder of the floor polygon after subtracting hallway polygons |
| **Core node** | Fixed anchor point for vertical circulation (stairwell, elevator shaft) |
| **Travel distance** | Shortest walkable path from any floor point to the nearest core node |

### 1.2 Initialization Parameters (fixed per floor)

| Parameter | Type | Description |
|---|---|---|
| `floor_polygon` | `list[tuple[float,float]]` | Vertices of the floor boundary in XY (m) |
| `elevation` | `float` | Z height of this floor (m) |
| `hallway_width` | `float` | Minimum clear hallway width (m); default 1.5 |
| `span_x` | `float` | Column grid spacing in X (m) |
| `span_y` | `float` | Column grid spacing in Y (m) |
| `core_locations` | `list[tuple[float,float]]` | XY positions of elevator / stairwell cores |
| `max_travel_distance` | `float` | Maximum allowed walking distance to a core (m); default 45.0 |
| `snap_tolerance` | `float` | Distance within which endpoints are merged (m); default 0.10 |
| `orthog_angle_threshold` | `float` | Skeleton edges within this angle of 0°/90° are snapped (deg); default 22.5 |
| `pruning_min_length` | `float` | Skeleton branches shorter than this are pruned (m); default `hallway_width` |

---

## 2. Generation Pipeline

```
Input: floor_polygon, core_locations, grid parameters

Step 1 – Medial Axis
    Compute medial axis of floor_polygon
    Represent result as a planar graph G = (V, E)

Step 2 – Pruning
    Remove edges whose length < pruning_min_length (noise branches)
    Remove degree-1 vertices (leaves) that are not near a core node

Step 3 – Orthogonalization
    For each edge e in G:
        θ = angle of e relative to X-axis
        If θ is within orthog_angle_threshold of 0° or 90°: snap e to that axis
        Else: split e at its midpoint; route two orthogonal sub-edges to the midpoint
    Re-merge vertices within snap_tolerance

Step 4 – Core Attraction
    For each core node c:
        Find nearest skeleton vertex v
        If dist(c, v) ≤ 2 × hallway_width: replace v with c
        Else: insert new edge from v to c (orthogonalized)

Step 5 – Grid Snapping
    For each vertex v in the orthogonalized skeleton:
        Snap v.x to nearest column grid line
        Snap v.y to nearest column grid line
    Re-check that all snapped edges remain inside floor_polygon;
    clip any protruding segment back to the boundary (Boolean intersection)

Step 6 – Boundary Clip
    Intersect each skeleton edge with floor_polygon
    Discard any segment outside

Step 7 – Buffering
    Buffer each skeleton edge by hallway_width / 2
    Union all resulting rectangles → hallway_polygon

Step 8 – Room Zone
    room_zone = floor_polygon − hallway_polygon   (Boolean difference)

Output: hallway_polygon, room_zone, skeleton_graph
```

---

## 3. Functional Requirements

### FR-1  Medial Axis Computation
- The algorithm MUST accept any simple (non-self-intersecting) polygon, including convex,
  L-shaped, T-shaped, U-shaped, and rectangular footprints.
- The medial axis MUST be computed entirely within the interior of the polygon (no axis
  vertex outside the boundary).

### FR-2  Pruning
- Branches shorter than `pruning_min_length` MUST be removed.
- No pruning is applied to edges that connect two core nodes or a core node to the
  main skeleton.

### FR-3  Orthogonalization
- After orthogonalization, every skeleton edge MUST be either horizontal (±0°) or
  vertical (±90°) relative to the column grid orientation.
- The orthogonalized graph MUST remain connected (no isolated sub-graphs).
- Vertex merging uses `snap_tolerance`; vertices closer than this distance are merged
  into their geometric centroid.

### FR-4  Core Attraction
- Every core node MUST be represented by at least one skeleton vertex after this step.
- The inserted edges connecting cores to the skeleton MUST also be orthogonal.

### FR-5  Grid Snapping
- All skeleton vertices MUST lie on column grid intersections after snapping.
- If snapping a vertex would push a segment outside `floor_polygon`, the vertex is
  snapped to the closest grid point that keeps the segment inside.

### FR-6  Boundary Safety
- No part of `hallway_polygon` may extend outside `floor_polygon`.
- The Boolean difference (`floor_polygon − hallway_polygon`) MUST produce a valid
  polygon (no self-intersections, no slivers narrower than `hallway_width / 4`).

### FR-7  Connectivity
- The skeleton graph after Step 5 MUST be a connected graph if `core_locations` is
  non-empty.
- If the polygon naturally yields a disconnected skeleton (e.g., two separate wings),
  the algorithm MUST insert a bridging edge along the shortest orthogonal path that
  stays inside the polygon.

### FR-8  Travel Distance
- For every point in `room_zone`, the shortest walkable path (through `hallway_polygon`)
  to the nearest core node MUST be ≤ `max_travel_distance`.
- If this constraint is violated, the algorithm MUST extend or widen the skeleton until
  the constraint is satisfied, or raise a `TravelDistanceViolation` error with the
  problematic region identified.

### FR-9  Hallway Width
- The clear width of `hallway_polygon` at any cross-section MUST be ≥ `hallway_width`.
- The algorithm MUST NOT produce pinch-points below `hallway_width` at grid-snapping
  junctions.

### FR-10  Output Validity
- `hallway_polygon` and `room_zone` MUST together exactly tile `floor_polygon`
  (no gaps, no overlaps): `area(hallway) + area(room_zone) == area(floor)` within
  floating-point tolerance (1e-4 m²).

---

## 4. Classes to Implement

### 4.1 `HallwayParams`  (`src/models/hallway.py`)

Dataclass holding all initialization parameters (see §1.2).

Computed properties:
- `grid_origin_x`, `grid_origin_y` — origin of column grid (default: polygon AABB min corner)
- `min_branch_length` → alias for `pruning_min_length`

Validation:
- `hallway_width > 0`
- `span_x > 0`, `span_y > 0`
- `max_travel_distance > 0`
- `snap_tolerance < hallway_width / 2` (snap must not merge unrelated vertices)
- `orthog_angle_threshold` ∈ (0, 45) degrees
- `floor_polygon` has ≥ 3 distinct vertices and is non-self-intersecting

### 4.2 `SkeletonGraph`  (`src/models/hallway.py`)

Lightweight graph: `nodes: list[tuple[float,float]]`, `edges: list[tuple[int,int]]`.

| Method | Description |
|---|---|
| `from_medial_axis(polygon)` | Class method — compute and store raw medial axis |
| `prune(min_length, protected_nodes)` | Remove short leaf branches; skip protected |
| `orthogonalize(angle_threshold, snap_tol)` | Snap edges; re-merge close vertices |
| `attract_cores(core_locations, hallway_width)` | Attach core nodes to nearest vertex |
| `snap_to_grid(span_x, span_y, origin, polygon)` | Snap vertices to grid; clip to polygon |
| `is_connected()` | Return `True` if graph has exactly one connected component |
| `bridge_components(polygon)` | Insert shortest orthogonal bridging edge |
| `travel_distances(core_nodes)` | BFS/Dijkstra from cores; return dict[node_idx → float] |

### 4.3 `HallwayLayout`  (`src/models/hallway.py`)

Dataclass produced by the generation pipeline.

| Field | Type | Description |
|---|---|---|
| `params` | `HallwayParams` | Input parameters |
| `skeleton` | `SkeletonGraph` | Final orthogonal skeleton |
| `hallway_polygon` | OCC `TopoDS_Shape` | 2-D hallway area (wire / face) |
| `room_zone` | OCC `TopoDS_Shape` | Remaining floor area |

| Method | Description |
|---|---|
| `generate(params)` | Class method — full pipeline Steps 1–8; returns `HallwayLayout` |
| `max_travel_distance_actual()` | Compute worst-case travel distance in the layout |
| `hallway_area_ratio()` | `area(hallway) / area(floor)` — lower is more efficient |
| `validate()` | Run all FR checks; return list of violation strings (empty = pass) |

---

## 5. Quality Gates

Quality gates are automated checks that MUST pass before the feature is considered complete.

### QG-1  Unit — Polygon Types
Test that `HallwayLayout.generate()` returns a valid layout (no exception, `validate()`
returns `[]`) for each of the following polygon shapes:
- Rectangle (20 × 10 m)
- L-shape
- T-shape
- U-shape
- Irregular convex polygon (≥ 6 vertices)

### QG-2  Unit — Boundary Safety (FR-6)
Assert `hallway_polygon` ⊂ `floor_polygon` for all QG-1 test polygons.
Use a 1e-3 m tolerance for boundary membership checks.

### QG-3  Unit — Area Conservation (FR-10)
For all QG-1 polygons:
```
|area(hallway) + area(room_zone) - area(floor)| < 1e-4 m²
```

### QG-4  Unit — Minimum Width (FR-9)
Sample the hallway polygon at regular intervals (every 0.1 m along each skeleton edge)
and assert the local half-width is ≥ `hallway_width / 2` at every sample point.

### QG-5  Unit — Orthogonality (FR-3)
After `SkeletonGraph.orthogonalize()`, for every edge (u, v):
```
angle = atan2(v.y - u.y, v.x - u.x) mod 90°
assert angle < 0.1°          # effectively 0° or 90°
```

### QG-6  Unit — Core Connectivity (FR-7, FR-4)
Given one or more core locations, assert every core node appears in `skeleton.nodes`
and the graph is connected (`skeleton.is_connected() == True`).

### QG-7  Unit — Travel Distance (FR-8)
For a 20 × 10 m rectangle with a single core at the centre, and
`max_travel_distance = 15 m`, assert `max_travel_distance_actual() ≤ 15`.

### QG-8  Unit — Pruning
Create a thin peninsular polygon with an obvious short stub branch. Assert the stub
is removed and the main spine is retained.

### QG-9  Unit — Grid Alignment (FR-5)
After `snap_to_grid()`, for every node `(x, y)` in the skeleton:
```
assert (x - origin_x) % span_x < snap_tolerance  or  same for Y
```

### QG-10  Integration — Full Pipeline
Instantiate `HallwayLayout.generate()` on a realistic floor (20 × 20 m, 4 × 4 m grid,
two core locations, `hallway_width = 1.8 m`). Assert:
- `validate()` returns `[]`
- `hallway_area_ratio() < 0.30`  (less than 30 % of floor is hallway)
- `max_travel_distance_actual() ≤ max_travel_distance`

### QG-11  Regression — Known Failure Mode: Corner Problem
Input a floor polygon with a sharp re-entrant corner. Assert the algorithm does NOT
produce a hallway segment that exits the polygon boundary (FR-6 is never violated).

### QG-12  Error Handling
Input a polygon where travel-distance cannot be satisfied with any skeleton.
Assert `TravelDistanceViolation` is raised and includes a description of the
unreachable region.

---

## 6. Relationship to Existing Components

```
HallwayParams ──► ColumnGrid (span_x, span_y)    (reuse for grid snapping)
              └──► BuildingMass floors             (provides floor_polygon per floor)

SkeletonGraph.snap_to_grid() ──► ColumnGrid.snap_point()   (new method needed)

HallwayLayout.hallway_polygon ──► SubtractionConfig        (future: treated as a subtractor)
HallwayLayout.room_zone       ──► Room packing algorithm   (future work)
```

---

## 7. Visual Test

`test/userInteraction/test_hallway.py`

Displays a single floor of a 20 × 20 m building with:
- Two core nodes (northwest and southeast corners)
- Column grid 4 × 4 m
- `hallway_width = 1.8 m`

Renders:
- Floor polygon outline (grey)
- Column grid dots (light blue)
- Raw medial axis (dashed yellow)
- Orthogonalized + snapped skeleton (solid orange)
- Hallway polygon (filled semi-transparent red)
- Room zones (filled semi-transparent green)
- Core nodes (solid blue circles)

---

## 8. Out of Scope

The following are explicitly **not** part of this requirement:

- 3-D extrusion of the hallway polygon into a volumetric solid (future work).
- Room packing / room subdivision within the room zone (future work).
- Multi-floor coordination (linking stairwell cores vertically — future work).
- Fire / egress code validation beyond maximum travel distance.
- Non-orthogonal (diagonal) hallways.
