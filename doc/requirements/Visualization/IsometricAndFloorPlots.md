# Visualization — Isometric Rendering & Per-Floor Plan Grid

## 1. Goal

Two new visual outputs for inspecting a generated `Individuum`:

| Output | Purpose |
|---|---|
| **Isometric rendering** | Architectural overview of the subtracted building mass in a standard isometric projection |
| **Per-floor plan grid** | Grid of 2D floor polygon plots — one subplot per floor — to verify how subtractions alter each floor plate |

---

## 2. Libraries

| Feature | Library | Notes |
|---|---|---|
| Isometric 3D rendering | `matplotlib` + `mpl_toolkits.mplot3d` | `Poly3DCollection` for filled faces; `elev=35.264°, azim=45°` gives true isometric projection |
| Per-floor plan grid | `matplotlib` subplots + `matplotlib.patches.Polygon` | 2D polygon fill per floor |
| Geometry extraction | OCC `TopExp_Explorer` | Walks edges of `floor.polygon_wire` to collect ordered `(x, y, z)` vertices |

No new conda packages are required. Verify matplotlib is present:
```bash
conda run -n pyoccEnv python -c "import matplotlib; print(matplotlib.__version__)"
```

---

## 3. Shared Extraction Utility

Both features share a single geometry extraction primitive.

### 3.1 `extract_wire_loops(wire_shape)`

**Location:** `src/models/wire_utils.py` (new file, or inlined in the test scripts)

**Signature:**
```python
def extract_wire_loops(wire_shape: TopoDS_Shape) -> list[list[tuple[float, float, float]]]:
```

**Behaviour:**
- If `wire_shape` is a single `TopoDS_Wire`: returns one loop of `(x, y, z)` points, one point per edge start vertex.
- If `wire_shape` is a `TopoDS_Compound` (floor with holes after subtraction): iterates sub-shapes first, returns one list of points per wire loop. The first loop is the outer boundary; subsequent loops are holes (courtyards, notches).

**Core OCC pattern:**
```python
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_EDGE
from OCC.Core.BRep import BRep_Tool

def _points_from_wire(wire):
    pts = []
    exp = TopExp_Explorer(wire, TopAbs_EDGE)
    while exp.More():
        edge = exp.Current()
        curve, u0, _ = BRep_Tool.Curve(edge)
        p = curve.Value(u0)
        pts.append((p.X(), p.Y(), p.Z()))
        exp.Next()
    return pts
```

For compound wires, iterate `TopAbs_WIRE` sub-shapes within the compound and call `_points_from_wire` on each.

---

## 4. Feature A — Isometric Rendering

### 4.1 Script

`test/userInteraction/test_individuum_iso.py`

### 4.2 Implementation Steps

**Step 1 — Build geometry**
- Create `IndividuumParams` and a random `Individuum` (same setup as `test_individuum.py`).
- Call `individuum.build()` → `(original_mass, subtracted_mass, config)`.

**Step 2 — Extract floor geometry**
- For each `floor` in `subtracted_mass.floors`:
  - Call `extract_wire_loops(floor.polygon_wire)` to get polygon loop(s) at `z = floor.elevation`.
  - The same loop elevated by `floor.floor_height` gives the top cap.

**Step 3 — Build `Poly3DCollection` faces**

For each floor, construct three sets of polygons:

| Face type | Description |
|---|---|
| **Bottom cap** | Polygon loop at `z = floor.elevation` |
| **Top cap** | Same loop at `z = floor.elevation + floor.floor_height` |
| **Wall quads** | One quad per edge: connects corresponding bottom and top edge vertices |

For floors with holes (compound wire), the outer loop contributes cap faces; inner loops define voids — simply omit or clip the corresponding wall quads to leave openings visible.

**Step 4 — Render**
- Create `fig, ax = plt.subplots(subplot_kw={"projection": "3d"})`.
- Add `Poly3DCollection(faces, ...)` with:
  - Face color: light grey (`#e8e8e8`), alpha 0.85 for subtracted mass.
  - Edge color: `#444444`, line width 0.6.
- Apply isometric camera:
  ```python
  ax.view_init(elev=35.264, azim=45)
  ax.set_box_aspect([bbox_width, bbox_depth, total_height])
  ```
- Optionally overlay the original maximal volume as a faint dashed outline (edges only, no fill).
- Turn off axis ticks and grid for a clean architectural look.

**Step 5 — Output**
- Show interactively (`plt.show()`) by default.
- Accept an optional `--save path/to/output.png` CLI argument for non-interactive export.

### 4.3 Color Scheme

| Element | Color | Alpha |
|---|---|---|
| Subtracted mass faces | `#e8e8e8` (off-white) | 0.85 |
| Mass edges | `#444444` (dark grey) | 1.0 |
| Original volume outline | `#888888` (mid grey), dashed | 0.3 |
| Floor plate top caps | `#ffffff` (white) | 1.0 |

---

## 5. Feature B — Per-Floor Plan Grid

### 5.1 Script

`test/userInteraction/test_individuum_floors.py`

(Alternatively: a second figure produced by `test_individuum_iso.py` when run with `--floors` flag.)

### 5.2 Implementation Steps

**Step 1 — Build geometry**
- Same individuum build as Feature A (can share setup code if in the same script).

**Step 2 — Extract 2D polygons**
- For each `floor` in `subtracted_mass.floors`:
  - Call `extract_wire_loops(floor.polygon_wire)`.
  - Keep only `(x, y)` — discard z (all points share the same elevation within a floor's wire).

**Step 3 — Create subplot grid**
- Determine grid layout: `n_cols = min(3, num_floors)`, `n_rows = ceil(num_floors / n_cols)`.
- `fig, axes = plt.subplots(n_rows, n_cols, ...)` with equal aspect ratio per axis.

**Step 4 — Draw per floor**

For each floor subplot:
1. Draw the original footprint polygon as a faint dashed outline (`--`, `#aaaaaa`).
2. For each loop returned by `extract_wire_loops`:
   - If it is the **outer loop**: draw as a filled `matplotlib.patches.Polygon` (light blue fill, dark edge).
   - If it is a **hole loop** (courtyards, notches): draw as a filled patch in white to represent the void.
3. Set title: `Floor {floor.index}  z = {floor.elevation:.1f} m`.
4. Set equal axis limits across all subplots (shared XY range = building bbox).
5. Hide axis ticks for a clean look.

**Step 5 — Output**
- Show interactively or save as PNG (same CLI convention as Feature A).

### 5.3 Color Scheme

| Element | Color | Style |
|---|---|---|
| Original footprint | `#aaaaaa` | Dashed outline, no fill |
| Floor polygon (solid area) | `#cce0ff` (light blue) | Filled, dark blue edge |
| Void / hole area | `#ffffff` (white) | Filled patch over solid fill |
| Subplot background | `#f5f5f5` | Axes face color |

---

## 6. Implementation Order

1. `src/models/wire_utils.py` — shared extraction utility (needed by both scripts)
2. `test/userInteraction/test_individuum_floors.py` — simpler; pure 2D; validates extraction utility
3. `test/userInteraction/test_individuum_iso.py` — builds on extraction utility; adds 3D face construction

---

## 7. File Overview

```
src/
└── models/
    └── wire_utils.py                          # NEW — extract_wire_loops()

test/
└── userInteraction/
    ├── test_individuum_floors.py              # NEW — per-floor 2D plan grid
    └── test_individuum_iso.py                 # NEW — isometric 3D matplotlib rendering
```

---

## 8. Open Decisions

| Question | Options |
|---|---|
| One combined script or two separate scripts? | Two separate scripts follow the existing convention; one combined script is more convenient to run |
| Interactive or static PNG export? | Interactive by default, `--save` flag for PNG |
| Include original maximal volume in isometric view? | Yes (faint dashed outline) or No (cleaner) |
| Hole rendering in floor plan? | Filled white patch (simple) or `matplotlib.path.Path` with winding rule (correct for overlapping holes) |
