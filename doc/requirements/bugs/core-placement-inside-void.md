# Bug: Building Core Placed Inside Subtracted Void

**Status:** Open
**Affected module:** `src/models/building_core_engine.py` → `find_building_cores()`
**Triggered by:** `Individuum.build()` when `core_generation_enabled = True`

---

## 1. Problem Description

A `BuildingCore` can be placed at a position that is inside a subtracted void (courtyard,
atrium, corner notch, stilt zone), making the core geometrically outside the remaining
building mass.  The core then has no physical meaning — the circulation/evacuation zone it
represents does not exist in the actual structure.

---

## 2. Root Cause

`find_building_cores()` places candidates in two situations:

| Placement trigger | Where the candidate comes from |
|---|---|
| Step 1 (seed) | Centroid of the ground-floor footprint *edge* midpoints |
| Step 2 (iterative) | Midpoint of the farthest uncovered footprint face |

In both cases the raw candidate position is then passed to `_snap_to_column_grid()`, which
iterates **all** column-grid cells across the original bounding box — including cells that
lie entirely inside a subtracted void — and returns the nearest cell center.

**No check is performed to verify that the snapped center (or the raw candidate) falls
within the solid material of the subtracted building mass.**

### Centroid-inside-void scenario

After subtraction the ground-floor `polygon_wire` is a compound that includes both the outer
boundary and the inner boundary of any cut (courtyard).  Computing the centroid as the
average of *all* edge midpoints (inner + outer) biases the centroid towards the interior of
a central courtyard, which is exactly the subtracted region.

### Snap-into-void scenario

Even when the raw candidate is on valid material, `_snap_to_column_grid()` may move it to
the nearest column-grid cell center.  If the nearest cell center lies inside a void the core
ends up there regardless.

---

## 3. Failing Example

```
Footprint: 50 × 50 m rectangle
Subtractor: 20 × 20 m courtyard centered at (25, 25) spanning full height

find_building_cores() computes:
  centroid of outer-ring + inner-ring midpoints → approx (25, 25)
  nearest column-grid cell center → also near (25, 25)
  → BuildingCore placed at (25, 25) — inside the courtyard
```

---

## 4. Required Fix

### 4.1 Guard in `_snap_to_column_grid`

After selecting the best cell (or keeping the raw candidate), **verify that the resulting
center lies inside the subtracted mass ground-floor solid** before accepting it.

Extend the signature:

```python
def _snap_to_column_grid(
    px: float,
    py: float,
    column_grid: ColumnGrid,
    ground_floor_solid,          # TopoDS_Shape — ground floor solid after subtraction
) -> BuildingCore | None:        # None if no valid cell found
```

Validation step (after selecting `best_cx`, `best_cy`):

1. Classify the 3D point `(center_x, center_y, z_test)` where
   `z_test = ground_floor_elevation + floor_height / 2` against the ground-floor solid using
   `BRepClass3d_SolidClassifier`.
2. Accept the position if the classifier reports `TopAbs_IN`.
3. If the best cell is invalid, iterate all remaining cells sorted by distance and repeat
   the check until a valid cell is found.
4. If no cell passes — fall back to the raw candidate `(px, py)` and check it; if that also
   fails return `None` so the caller can skip this candidate.

### 4.2 Update `find_building_cores` signature

Pass the ground-floor solid to each `_snap_to_column_grid` call:

```python
ground_floor_solid = mass.floors[0].solid
```

### 4.3 Handle `None` return in placement loop

**Seed (Step 1):**
If the centroid snap returns `None`, try each face midpoint in turn (sorted by centrality)
until a valid position is found.  If none is found raise `ValueError` with a descriptive
message.

**Iterative (Step 2):**
If the snap of the farthest face midpoint returns `None`, the face midpoint itself is
guaranteed to be on the boundary — use the raw face-midpoint position as the fallback core
center (without snapping) so placement always progresses.

### 4.4 Extractor note

The face-midpoint positions extracted from `polygon_wire` are **on** the footprint boundary,
not inside the void, so they are always valid fallback positions.  The bug only manifests
during the snap step that moves the candidate off the boundary into the interior.

---

## 5. OCC API for Point Classification

```python
from OCC.Core.BRepClass3d import BRepClass3d_SolidClassifier
from OCC.Core.gp import gp_Pnt
from OCC.Core.TopAbs import TopAbs_IN

classifier = BRepClass3d_SolidClassifier(solid)
classifier.Perform(gp_Pnt(cx, cy, z_test), tolerance=1e-3)
is_inside = classifier.State() == TopAbs_IN
```

The classifier must be re-instantiated (or reset with `.Load(solid)`) for each solid it
tests against — it does **not** support changing the solid after construction.

---

## 6. Acceptance Criteria

1. When a subtractor creates a central courtyard spanning ≥ 50 % of the footprint area,
   no `BuildingCore` center falls inside the courtyard rectangle.
2. When every column-grid cell center is inside a void, the engine falls back to raw face
   midpoints without raising an unhandled exception.
3. All 37 existing unit tests in `test/models/test_building_core.py` continue to pass.
4. A new unit test in `test/models/test_building_core.py` covering the courtyard scenario
   (criterion 1) is added and passes.

---

## 7. Files to Modify

| File | Change |
|---|---|
| `src/models/building_core_engine.py` | Add OCC solid classification; update `_snap_to_column_grid`; update fallback logic in `find_building_cores` |
| `test/models/test_building_core.py` | Add regression test for courtyard + core placement |
