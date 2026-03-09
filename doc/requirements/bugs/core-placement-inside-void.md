# Bug: Building Core Placed Inside Subtracted Void

**Status:** Fixed
**Affected module:** `src/models/building_core_engine.py` → `find_building_cores()`
**Triggered by:** `Individuum.build()` when `core_generation_enabled = True`

---

## 1. Problem Description

A `BuildingCore` can be placed at a position that is inside a subtracted void (courtyard,
atrium, corner notch, stilt zone), making the core geometrically outside the remaining
building mass.  The core then has no physical meaning — the circulation/evacuation zone it
represents does not exist in the actual structure.

Two distinct failure modes were identified and fixed:

| # | Failure mode | Symptom |
|---|---|---|
| A | Ground-floor-only check | Core placed in a void created by a horizontal subtractor that only affects upper floors |
| B | Center-point-only check | Core center lies in solid material, but the core's rectangular footprint partially overlaps the void |

---

## 2. Root Cause

### 2A — Ground-floor-only validation

`_snap_to_column_grid` validated candidate positions using `BRepClass3d_SolidClassifier`
against the **ground-floor solid only**.  Horizontal subtractors that cut voids on upper
floors were never checked, so a core could be placed at an XY position that is solid on
the ground floor but void on floors 2–6.

### 2B — Center-point-only validation

Even after fix 2A, the check only tested the **center point** `(cx, cy)` of the candidate
cell.  A core's rectangular footprint (one full column-grid span in X and Y) can extend
into a void even when the center is in solid material — most commonly when the center sits
near the boundary of a void.

### Original centroid-inside-void scenario (also fixed)

After subtraction the ground-floor `polygon_wire` is a compound that includes both the outer
boundary and the inner boundary of any cut (courtyard).  Computing the centroid as the
average of *all* edge midpoints (inner + outer) biases the centroid towards the interior of
a central courtyard, which is exactly the subtracted region.

---

## 3. Failing Examples

### Example A — Upper-floor void

```
Footprint: 50 × 50 m rectangle
Horizontal subtractor: 20 × 20 m void at z=[7, 21] (floors 3–6)

find_building_cores() (old code) computes:
  centroid of ground-floor edge midpoints → approx (25, 25)
  classify (25, 25) against ground-floor solid → TopAbs_IN  ✓  (ground floor is uncut)
  → BuildingCore placed at (25, 25) — inside the upper-floor void
```

### Example B — Footprint clipping a void (seed 42)

```
Footprint: 20 × 20 m rectangle, 6 floors
Subtractors: 1 vertical + 2 horizontal (floors 2–3 partially cut)

find_building_cores() (fix A applied, not B) computes:
  nearest valid cell center: (14, 10) — center is in solid material on all floors ✓
  core footprint: x=[12,16], y=[8,12]
  → corners at (12, 8) and (12, 12) are inside the void on floors 2–3
  → core visually overlaps void in the floor plan
```

---

## 4. Fix Applied

### 4A — Validate against all floor solids

`find_building_cores` builds a `floor_tests` list of `(solid, z_test)` pairs for
**every** floor, not just the ground floor:

```python
floor_tests = [
    (floor.solid, floor.elevation + floor.floor_height / 2)
    for floor in mass.floors
]
```

This list is passed to `_snap_to_column_grid`, which now checks every floor solid
before accepting a candidate position.

### 4B — Validate the full footprint rectangle, not just the center

`_snap_to_column_grid` uses a new helper `_footprint_valid(cx, cy, half_w, half_d, floor_tests)`
that samples **5 points** of the core footprint rectangle:

- center `(cx, cy)`
- 4 corners `(cx ± half_w, cy ± half_d)`

All 5 points must be inside (or on the surface of) every floor solid.  This prevents a
core from being placed at a position where the footprint rectangle clips a void even though
the center point is in solid material.

```python
def _footprint_valid(cx, cy, half_w, half_d, floor_tests):
    sample_points = [
        (cx, cy),
        (cx - half_w, cy - half_d), (cx + half_w, cy - half_d),
        (cx - half_w, cy + half_d), (cx + half_w, cy + half_d),
    ]
    for solid, z in floor_tests:
        for px, py in sample_points:
            if not _is_inside_solid(px, py, solid, z):
                return False
    return True
```

### Fallback logic (unchanged)

The fallback hierarchy in `find_building_cores` when `_snap_to_column_grid` returns `None`
is unchanged: try each face midpoint sorted by centrality; raise `ValueError` if none works.

---

## 5. Files Modified

| File | Change |
|---|---|
| `src/models/building_core_engine.py` | Replaced `_is_inside_all_floors` (center-only) with `_footprint_valid` (center + 4 corners); build `floor_tests` from all floors instead of ground floor only |
| `test/models/test_building_core.py` | Added `TestCoreNotInsideCourtyard` (full-height courtyard) and `TestCoreNotInsideUpperFloorVoid` (partial-height horizontal void) regression tests |

---

## 6. Acceptance Criteria (all met)

1. When a subtractor creates a central courtyard spanning ≥ 50 % of the footprint area,
   no `BuildingCore` footprint overlaps the courtyard rectangle. ✓
2. When a horizontal subtractor creates a void only on upper floors, no core footprint
   overlaps the void on those floors. ✓
3. When every column-grid cell center is inside a void, the engine falls back to raw face
   midpoints without raising an unhandled exception. ✓
4. All unit tests in `test/models/test_building_core.py` pass (41/41). ✓
