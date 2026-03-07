# BuildingMass – Data Structure Plan

## Goal

The data structure must give access to:
- The full building as a collection of floors
- Each floor's solid geometry (the extruded volume)
- Each floor's polygon wire (the plan outline at that level)
- Metadata per floor: floor number, elevation, height
- Metadata for the whole building: total height, number of floors, input polygon

---

## Proposed structure

### `FloorData` (per floor)

Holds everything belonging to one floor.

```
FloorData
├── index          : int          – 0-based floor number (0 = ground floor)
├── elevation      : float        – Z position of the bottom face (= index × floor_height)
├── floor_height   : float        – height of this specific floor (allows variable heights later)
├── solid          : TopoDS_Shape – extruded solid volume for this floor
└── polygon_wire   : TopoDS_Shape – closed wire (plan outline) at the bottom face elevation
```

**Why separate `solid` and `polygon_wire`?**
- The solid is needed for Boolean operations, volume/area analysis, and export.
- The wire is needed for rendering the floor plan, offset operations (setbacks), and 2D drawings.

---

### `BuildingMass`

Top-level container produced by the generation algorithm.

```
BuildingMass
├── polygon_points : list[tuple[float, float, float]]  – original input polygon (XY plane)
├── floor_height   : float                             – uniform floor height (kept for reference)
├── num_floors     : int                               – total number of floors
├── total_height   : float                             – = floor_height × num_floors
└── floors         : list[FloorData]                   – ordered list, index 0 = ground floor
```

---

## Class diagram

```
BuildingMass
│
├── polygon_points: list[tuple]
├── floor_height: float
├── num_floors: int
├── total_height: float  (derived)
│
└── floors: list[FloorData]
            │
            ├── index: int
            ├── elevation: float   (derived: index × floor_height)
            ├── floor_height: float
            ├── solid: TopoDS_Shape
            └── polygon_wire: TopoDS_Shape
```

---

## Access patterns

| Use case | Access |
|---|---|
| Get the solid of floor 2 | `mass.floors[2].solid` |
| Get the plan wire of the ground floor | `mass.floors[0].polygon_wire` |
| Iterate all floor solids | `[f.solid for f in mass.floors]` |
| Get the elevation of floor 3 | `mass.floors[3].elevation` |
| Total building height | `mass.total_height` |

---

## Extension points

These fields are intentionally left out for now but should be kept in mind:

| Field | Where | Purpose |
|---|---|---|
| `floor_height` per floor (variable) | `FloorData` | Already supported in structure — just pass different heights per floor |
| `top_wire` | `FloorData` | Wire at the top face, useful for setbacks between floors |
| `ceiling_solid` | `FloorData` | Separate slab geometry if structural detail is needed |
| `name / label` | `FloorData` | Human-readable floor name (e.g. "Ground Floor", "Level 2") |
| `use_type` | `FloorData` | Functional programme (residential, commercial, parking…) |
| `compound` | `BuildingMass` | A single merged `TopoDS_Compound` of all solids for fast export |

---

## Implementation notes

- `FloorData` should be a **dataclass** (`@dataclass`) — lightweight, no boilerplate, easy to add `__repr__`.
- `BuildingMass` can also be a dataclass, with `total_height` as a `field(init=False)` computed in `__post_init__`.
- Keep OCC geometry (`TopoDS_Shape`) inside the dataclass but do **not** try to serialize it directly — use STEP/BREP export when persistence is needed.
- The generation function in `floorgeneration.py` should return a `BuildingMass` instead of a plain `list[TopoDS_Shape]`.
