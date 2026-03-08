# Subtractive Form Generation – Requirements

## Source

Wang et al. (2019), "Subtractive Building Massing for Performance-Based Architectural Design
Exploration: A Case Study of Daylighting Optimization", *Sustainability* 11, 6965.

---

## 1. Principle Summary

The subtractive form generation principle starts from a **maximal solid volume** — the full
building mass as if nothing were removed — and produces architectural variants by **cutting
parts away** from that volume. Each removed part is called a **subtractor**.

By varying the number, size, and position of subtractors, the algorithm generates massings with
significant **topological variability**: the same starting box can produce courtyard buildings,
atrium towers, stepped cascades, pilotis/stilts, L-shapes, U-shapes, and combinations thereof.
This variability is what gives the principle its power for performance-based design exploration.

Crucially, many common passive energy-saving strategies (courtyards, atriums, setbacks, stilts)
are naturally expressed as subtractions from a rectangular block, making this principle both
architecturally legible and algorithmically compact.

### Two subtractor types

Both subtractor types are **rectangular box-shaped voids**. Each is defined by an XY position
and plan size, plus a Z range. The difference between them is their **vertical aspect ratio**
and the constraint enforced on that ratio:

| Type | Aspect ratio | Resulting feature |
|---|---|---|
| **Vertical subtractor** | Tall — spans many floors; height may equal or approach the full building height | Courtyard (enclosed void), atrium, corner notch, recess |
| **Horizontal subtractor** | Flat — limited vertical extent (< 30 % of total height, ≥ 1 floor height) | Stilt (void at base), cascade / setback roof (void at top), partial empty floor section |

Crucially, a horizontal subtractor does **not** remove a whole floor. It removes a portion of
the building volume at a specific height range. The architectural feature it creates (stilt,
setback, empty section) depends entirely on where it is placed vertically.

---

## 2. Mapping to the Current Data Model

The current `BuildingMass` is exactly the **maximal volume** from which subtractions are made.
Each `FloorData` holds two geometry objects that must both be updated after subtraction:

| Geometry | Role | How subtraction affects it |
|---|---|---|
| `FloorData.solid` | 3-D extruded solid (OCC `TopoDS_Shape`) | Boolean cut with the subtractor solid via `BRepAlgoAPI_Cut` |
| `FloorData.polygon_wire` | 2-D plan outline wire at floor elevation | Must reflect the new floor footprint after the cut |

**Both** vertical and horizontal subtractors modify `solid` and `polygon_wire` for every floor
they overlap in Z. Neither type removes a whole floor — each one removes a partial box-shaped
region from the floors it intersects. The different architectural effects come from the shape and
placement of the box, not from the logic treating floors as units.

---

## 3. New Model: `Subtractor`

### 3.1 Shared structure

Both subtractor types share the same core fields — they are both rectangular boxes defined by
an XY footprint and a Z range.

```
Subtractor  (base / shared fields)
├── x          : float   – X position of subtractor origin (within building footprint)
├── y          : float   – Y position of subtractor origin (within building footprint)
├── width      : float   – extent in X
├── depth      : float   – extent in Y
├── z_bottom   : float   – absolute Z of the bottom face of the subtractor box
└── z_top      : float   – absolute Z of the top face of the subtractor box
```

The OCC cutting solid is built as:
```
BRepPrimAPI_MakeBox(
    gp_Pnt(x, y, z_bottom),
    gp_Pnt(x + width, y + depth, z_top)
).Shape()
```

### 3.2 Subtractor types

```
SubtractorType  (enum)
├── VERTICAL     – tall void; height is large relative to plan dimensions
└── HORIZONTAL   – flat void; height < vertical_snap_threshold of total building height, ≥ 1 floor height
```

The type does not change the subtraction logic — it is metadata that:
- drives constraint validation (see Section 4)
- communicates design intent to the user and to any future optimiser

### 3.3 Vertical subtractor

A vertical subtractor is tall. Its top and/or bottom face may be **auto-aligned** (snapped) to
the top or bottom of the maximal volume when the gap between the face and the boundary is less
than `vertical_snap_threshold × total_height`. This alignment produces fully open-top or
open-bottom voids (atriums / courtyards). At least one face (top or bottom) must satisfy the
snap criterion, otherwise the subtractor is deactivated.

### 3.4 Horizontal subtractor

A horizontal subtractor is flat. Its vertical extent must satisfy:

```
floor_height ≤ (z_top - z_bottom) < horizontal_max_height_ratio × total_height
```

If above the upper limit → the height is clipped down to `horizontal_max_height_ratio × total_height`.
If below the lower limit → deactivated (not applied).

The architectural effect depends on vertical placement:
- `z_bottom = 0` → stilts (void at base, building floats above ground)
- `z_top ≈ total_height` → cascade / setback roof
- mid-range → partial empty floor section

### 3.5 Combined model

```
SubtractionConfig
├── vertical_subtractors        : list[Subtractor]   (SubtractorType.VERTICAL)
├── horizontal_subtractors      : list[Subtractor]   (SubtractorType.HORIZONTAL)
├── vertical_snap_threshold     : float = 0.30   – snap fraction for vertical subtractors
└── horizontal_max_height_ratio : float = 0.30   – max height fraction for horizontal subtractors
```

---

## 4. Constraints

These rules keep subtracted massings architecturally meaningful. They are applied during
a validation/clamping pass before any geometry is created.

### 4.1 Horizontal plan size constraint (both types, user-defined)

The plan dimensions (`width`, `depth`) are constrained by a user-defined minimum and maximum
measured in column-grid spans:

| Condition | Action |
|---|---|
| `width` or `depth` > upper limit | Clip to upper limit |
| `width` or `depth` < lower limit | Deactivate the subtractor (skip it entirely) |

When two or more subtractors overlap and merge, the combined void can exceed the upper limit —
the constraint does not prevent this; it only constrains individual subtractors.

### 4.2 Vertical size constraint (configurable, defaults from paper)

Both thresholds live on `SubtractionConfig` and can be freely adjusted. The paper's values are
used as defaults.

**Vertical subtractors** — snap threshold:
```
vertical_snap_threshold : float = 0.30   # fraction of total_height
```
Top and/or bottom faces are auto-snapped to the maximal volume boundary if the gap is less than
`vertical_snap_threshold × total_height`. At least one face must qualify — otherwise the
subtractor is deactivated.

**Horizontal subtractors** — max height ratio:
```
horizontal_max_height_ratio : float = 0.30   # fraction of total_height
```
The vertical extent must be:
```
floor_height ≤ (z_top - z_bottom) < horizontal_max_height_ratio × total_height
```
If above the upper limit it is clamped. If below the lower limit the subtractor is deactivated.

### 4.3 Boundary constraint (user-defined, applies to vertical subtractors)

Controls whether a vertical subtractor can break through the outer face of the maximal volume:

| Setting | Effect |
|---|---|
| **Disabled** (open boundary) | If any face of the subtractor is close to the outer face of the maximal volume, it is snapped outward — creating an open notch or slot running through the outer wall |
| **Enabled** (closed boundary) | Any subtractor face close to the outer boundary is pushed inward — creating an enclosed interior void (courtyard, atrium) |

With the boundary constraint disabled, subtractors can push two or more separate building
volumes apart, enabling inter-building configurations.

### 4.4 Post-cut validity

If a boolean cut produces an empty, null, or geometrically invalid solid (checked via
`BRepCheck_Analyzer`), the subtractor is silently skipped for that floor.

---

## 5. Algorithm: Applying Subtractions

The subtraction process takes an existing `BuildingMass` and a `SubtractionConfig` and
returns a new `BuildingMass` with modified floors.

```
apply_subtractions(mass: BuildingMass, config: SubtractionConfig) -> BuildingMass
```

### Step 1 – Validate and clamp subtractors

Run all subtractors through the constraint checks (Section 4). Deactivated subtractors are
removed from the list. Oversized ones are clamped. Vertical subtractor faces are snapped to the
maximal volume boundary where applicable.

### Step 2 – Build all subtractor solids

For each active subtractor (both types), construct the OCC cutting box:

```
box = BRepPrimAPI_MakeBox(
          gp_Pnt(s.x,           s.y,           s.z_bottom),
          gp_Pnt(s.x + s.width, s.y + s.depth, s.z_top)
      ).Shape()
```

### Step 3 – Process each floor

For each `FloorData` with elevation range `[floor.elevation, floor.elevation + floor.floor_height]`,
collect all subtractor boxes that overlap this Z range:

```
active_subs = [box for (sub, box) in all_boxes
               if sub.z_bottom < floor.elevation + floor.floor_height
               and sub.z_top   > floor.elevation]
```

Apply all active subtractor boxes to the floor solid via sequential boolean cuts:

```python
result = floor.solid
for sub_box in active_subs:
    cut = BRepAlgoAPI_Cut(result, sub_box)
    if cut.IsDone() and not cut.Shape().IsNull():
        result = cut.Shape()
```

Then update the floor's `polygon_wire` to reflect the new footprint:

```
new_wire = extract_bottom_wire(result, elevation=floor.elevation)
```

**`extract_bottom_wire`**: Recovers the updated 2-D floor outline from the cut solid.
Iterates faces with `TopExp_Explorer(solid, TopAbs_FACE)`, selects the face at
`z ≈ floor.elevation` with a downward-pointing normal, then extracts all its wires.
This produces an accurate plan outline that may include concavities, notches, or interior
holes — without requiring a separate 2-D polygon boolean operation.

### Step 4 – Rebuild BuildingMass

All floors are kept (no floor is deleted as a unit). Each floor gets its updated `solid` and
`polygon_wire`. A new `BuildingMass` is returned with the same `polygon_points` (documenting
the original maximal footprint) and updated floor list.

---

## 6. Impact on `polygon_wire`

The `polygon_wire` of a floor after a vertical cut is **not** a simple polygon anymore — it may
be an L-shape, U-shape, or contain holes. OCC's BRep topology handles this correctly:

- `extract_bottom_wire` should return all wires on the bottom face (outer boundary + any
  inner boundary loops for through-holes such as atriums).
- Callers that previously assumed a single closed wire must be updated to handle a list of wires
  or a face with multiple wires.
- The `FloorData.polygon_wire` field type should be documented as "one or more wires describing
  the floor outline at its elevation", and may be extended to `polygon_face: TopoDS_Shape` (a
  planar face) so that area computation and rendering work uniformly.

---

## 7. File Layout

```
src/
└── models/
    ├── subtractor.py               (new) – VerticalSubtractor, HorizontalSubtractor,
    │                                       SubtractorType enum, SubtractionConfig dataclass
    └── subtraction_engine.py       (new) – apply_subtractions(), apply_vertical_cuts(),
                                            extract_bottom_wire()

test/
└── models/
    └── test_subtraction.py         (new) – unit tests for subtraction logic

test/userInteraction/
    └── test_subtraction.py         (new) – visual inspection: original mass vs. subtracted mass
```

---

## 8. OCC APIs Required

| Operation | OCC API |
|---|---|
| Build subtractor box | `BRepPrimAPI_MakeBox(gp_Pnt, gp_Pnt)` |
| Boolean cut solid | `BRepAlgoAPI_Cut(base, tool)` |
| Iterate faces of cut solid | `TopExp_Explorer(shape, TopAbs_FACE)` |
| Get face normal direction | `BRep_Tool.Surface(face)` → `gp_Dir` via `GeomLProp_SLProps` |
| Extract wire from face | `TopExp_Explorer(face, TopAbs_WIRE)` |
| Check solid validity | `BRepCheck_Analyzer(shape).IsValid()` |

All of these are already available in the `pythonocc-core` 7.9.3 environment.

---

## 9. Open Questions / Future Extensions

| Topic | Note |
|---|---|
| **Non-rectangular subtractors** | The paper uses rectangular (grid-aligned) subtractors. Non-rectangular (polygon) subtractors would require passing an arbitrary `TopoDS_Solid` as the cutting tool. |
| **Alignment to structural grid** | Subtractor positions could be snapped to `BuildingGrid` cell boundaries for structural coherence. |
| **Partial-height vertical subtractors** | Currently floor-aligned. A subtractor that spans partial floors (e.g. double-height void) requires `floor_start`/`floor_end` in fractional floors or absolute Z values. |
| **Gross floor area constraint** | The paper adjusts the maximal volume to hit a target GFA. This requires computing floor area via `GProp_GProps` + `BRepGProp.SurfaceProperties` after each subtraction and iterating. |
| **Core generation** | The paper adds a building core (stairs/lift shaft) as a fixed vertical element. This is the inverse: a volume that is **preserved** rather than subtracted, implemented as a constraint on subtractor placement. |
