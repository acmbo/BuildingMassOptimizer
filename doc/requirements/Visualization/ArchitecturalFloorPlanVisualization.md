# Architectural Floor Plan Visualization — Specification

## 1. Goal & Motivation

The current per-floor plan visualization (`test_individuum_viz.py`, Figure 2) is functional
but reads as a data plot rather than an architectural drawing.  The goal is to raise it to
something an architect would recognize: clear line-weight hierarchy, a structural column grid,
explicit distinction between outer building boundary and interior voids, and a modular API so
individual floor plots can be composed freely into any figure layout.

This document specifies the design intent, data flow, visual language, and implementation
contract for the enhanced floor plan visualization.

---

## 2. Design Intent — Thinking Like an Architect

In architectural practice, a floor plan is a **horizontal section cut** roughly 1 m above the
floor slab.  Every graphic decision communicates information through a strict convention:

### 2.1 Line-Weight Hierarchy

| Weight | What it represents | Typical width |
|---|---|---|
| **Heavy** | Cut elements — walls, columns, cores (the section cut passes through them) | 1.5–2.0 pt |
| **Medium** | Visible edges below the cut plane (floor slab edge, thresholds) | 0.5–0.8 pt |
| **Light** | Reference / construction lines — column grid, dimensions | 0.2–0.3 pt |
| **Hairline** | Hatch lines within solid material | 0.1–0.15 pt |

The outer building perimeter carries the **heaviest** line weight because it is the most
architecturally significant element.  Interior void boundaries (courtyard walls, atrium edges)
carry medium weight.  Column grid lines are always the thinnest element so they recede visually.

### 2.2 Material Hatching

Walls and slabs cut by the section plane are conventionally filled with a **45° diagonal
hatch** (or solid black for small scales).  For computational building studies at 1:200–1:500
scale, a light solid fill + thin hatch is readable without becoming noise.

### 2.3 Column Grid Language

Structural column grids are drawn as **thin dash-dot lines** spanning the full plan.  Column
positions are marked with a **filled circle or cross** (⊕) at every grid intersection.  Grid
lines are labelled numerically along X (1, 2, 3 …) and alphabetically along Y (A, B, C …),
following ISO/DIN convention.  Labels sit outside the building footprint in a margin zone.

### 2.4 Outer Boundary vs Interior Voids

An architect reads the plan in two passes:
1. The **outline** (thickest lines) defines the building's relationship to the site.
2. The **interior** (medium lines + fills) describes the usable floor area and the voids.

Voids (courtyards, atriums, notches) must read unambiguously as **absence of floor**: they
should be white or very light, surrounded by a wall of consistent thickness, and bounded by
a medium line.  The outer boundary — always the first loop returned by `extract_wire_loops` —
receives a heavier stroke and a thin exterior hatch to reinforce "this is the building edge."

### 2.5 Scale Bar & Annotations

Every architectural drawing carries a scale bar and a north arrow.  For computational
comparison plots a compact scale bar (showing 0–5 m and 0–10 m) in the lower-left corner
is sufficient.  A simple north-arrow glyph (↑N) in the upper-right corner anchors orientation.

---

## 3. Visual Vocabulary (Color & Style Palette)

All colors use hex strings.  The palette is intentionally low-saturation and paper-like.

| Token | Hex | Usage |
|---|---|---|
| `PAPER` | `#fafaf7` | Axes and figure background ("off-white paper") |
| `FLOOR_FILL` | `#e8ecf0` | Solid floor area fill (light cool grey) |
| `WALL_HATCH` | `#9aa8b8` | 45° hatch lines inside floor area |
| `VOID_FILL` | `#ffffff` | Interior courtyard / subtracted area |
| `VOID_EDGE` | `#4a6080` | Courtyard boundary line (medium weight) |
| `OUTER_EDGE` | `#1a2a3a` | Outer building boundary (heavy weight) |
| `GRID_LINE` | `#b0bcc8` | Column grid lines (light, dash-dot) |
| `GRID_LABEL` | `#6a7a8a` | Column grid axis labels |
| `COLUMN_DOT` | `#2a3a4a` | Filled circle at column intersections |
| `CORE_FILL` | `#c0d4f0` | Service core fill (light blue) |
| `CORE_EDGE` | `#1a3a80` | Service core boundary (medium weight) |
| `ORIG_FOOTPRINT` | `#cc8866` | Original footprint dashed reference outline |
| `SCALE_BAR` | `#1a2a3a` | Scale bar and labels |

---

## 4. Modular API — Single-Floor Drawing Function

The key architectural decision is to separate the **"draw one floor"** concern from the
**"arrange N floors in a figure"** concern.  This enables re-use: a single floor can be drawn
stand-alone for detail inspection, or composed with other floors into a comparison grid.

### 4.1 Primary Drawing Function

```python
def draw_floor_plan(
    ax: matplotlib.axes.Axes,
    floor: FloorData,
    *,
    column_grid: ColumnGrid | None = None,
    original_footprint: list[tuple[float, float]] | None = None,
    show_column_labels: bool = True,
    show_scale_bar: bool = True,
    show_north_arrow: bool = False,
    show_floor_label: bool = True,
    margin: float = 2.0,
    palette: dict | None = None,
) -> None:
```

**Responsibility:** Render a single `FloorData` into an already-created `Axes`.  All visual
layers are drawn in strict Z-order so later layers always sit on top.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `ax` | `Axes` | Target matplotlib axes (caller creates it) |
| `floor` | `FloorData` | Floor to visualize (contains `polygon_wire` and `cores`) |
| `column_grid` | `ColumnGrid \| None` | If provided, column grid lines + dots are drawn |
| `original_footprint` | `list[tuple] \| None` | XY points of the un-subtracted building outline; if provided, drawn as a dashed reference |
| `show_column_labels` | `bool` | Draw numeric/alpha axis labels outside the footprint |
| `show_scale_bar` | `bool` | Draw a compact scale bar in the lower-left corner |
| `show_north_arrow` | `bool` | Draw ↑N glyph in the upper-right corner |
| `show_floor_label` | `bool` | Set the axes title to `Floor {n}  z = {z:.1f} m` |
| `margin` | `float` | Extra space in model units added around the footprint bbox |
| `palette` | `dict \| None` | Override default color tokens (merged with defaults) |

### 4.2 Drawing Layers (Z-order, lowest to highest)

| Z | Layer name | What is drawn | Style |
|---|---|---|---|
| 1 | `paper` | Axes background fill | `PAPER` color |
| 2 | `original_footprint` | Dashed outline of the maximal footprint (optional) | `ORIG_FOOTPRINT`, dashed, no fill, 0.8 pt |
| 3 | `column_grid_lines` | Vertical + horizontal grid lines spanning the plan (optional) | `GRID_LINE`, dash-dot, 0.25 pt |
| 4 | `floor_fill` | Outer floor polygon filled (solid floor material) | `FLOOR_FILL` fill, no edge yet |
| 5 | `wall_hatch` | 45° hatch over the floor fill (thin lines, same bbox clip) | `WALL_HATCH`, 0.15 pt, angle 45° |
| 6 | `void_fill` | Interior hole loops filled white (courtyards, atriums) — punched through hatch | `VOID_FILL`, `VOID_EDGE` edge, 1.0 pt |
| 7 | `core_fill` | Service core rectangles | `CORE_FILL` fill, `CORE_EDGE` edge, 1.2 pt |
| 8 | `column_dots` | Filled circle at every column grid intersection (optional) | `COLUMN_DOT`, radius ≈ 0.15 m |
| 9 | `outer_edge` | Outer building boundary redrawn on top for maximum weight | `OUTER_EDGE`, solid, 1.8 pt |
| 10 | `void_edge` | Courtyard/notch boundary redrawn for correct weight | `VOID_EDGE`, solid, 1.0 pt |
| 11 | `core_edge` | Core boundaries redrawn | `CORE_EDGE`, solid, 1.2 pt |
| 12 | `column_labels` | Axis labels (numbers along X, letters along Y) outside margin (optional) | `GRID_LABEL`, 7 pt |
| 13 | `scale_bar` | Compact scale bar (optional) | `SCALE_BAR`, 7 pt |
| 14 | `north_arrow` | ↑N glyph (optional) | `SCALE_BAR`, 8 pt |

### 4.3 Axes Setup Contract

`draw_floor_plan` is responsible for:
- Setting `ax.set_aspect("equal")`.
- Setting `ax.set_facecolor(palette["PAPER"])`.
- Computing `xlim` and `ylim` from the union of all polygon points + `margin`.
- Removing tick marks and axis spines (`ax.set_axis_off()`).
- Setting the axes title if `show_floor_label` is True.

The caller is responsible for figure creation, subplot layout, and `plt.show()` / save.

---

## 5. Column Grid Visualization

### 5.1 Grid Lines

Draw one vertical line per entry in `column_grid.grid_lines_x` and one horizontal line per
entry in `column_grid.grid_lines_y`.  Lines span the full visible area (from `ylim[0]` to
`ylim[1]` for verticals, `xlim[0]` to `xlim[1]` for horizontals) so they extend into the
margin zone where labels sit.

Style: `linestyle=(0, (8, 4, 2, 4))` (dash-dot pattern), `linewidth=0.25`, `color=GRID_LINE`,
`alpha=0.9`, `zorder=3`.

### 5.2 Column Dots

At every intersection `(gx, gy)` of `grid_lines_x × grid_lines_y`, draw a filled circle.
Radius in data units ≈ `min(span_x, span_y) * 0.04`.  Color: `COLUMN_DOT`.  If the
intersection falls outside the original building footprint, draw with reduced alpha (0.35)
to signal a structural column that is outside the building perimeter (relevant for irregular
footprints).

### 5.3 Axis Labels

Place numeric labels ("1", "2", "3" …) centered below each vertical grid line, at
`y = ylim[0] - margin * 0.35`.  Place alphabetic labels ("A", "B", "C" …) centered to the
left of each horizontal grid line, at `x = xlim[0] - margin * 0.35`.  Fontsize 7 pt,
color `GRID_LABEL`.  Only draw if `show_column_labels=True`.

---

## 6. Outer Boundary vs. Interior Voids

`extract_wire_loops(floor.polygon_wire)` returns a list of loops where:
- `loops[0]` is the **outer boundary** (wound counter-clockwise in XY).
- `loops[1:]` are **interior voids** (wound clockwise, opposite winding).

The visualization must make this distinction visually unambiguous:

| Element | Edge weight | Edge style | Fill |
|---|---|---|---|
| Outer boundary | 1.8 pt | solid, `OUTER_EDGE` | `FLOOR_FILL` + hatch |
| Courtyard / void boundary | 1.0 pt | solid, `VOID_EDGE` | `VOID_FILL` (white) |

**Implementation note:** Use `matplotlib.path.Path` with reversed winding for holes (already
implemented in the existing `_make_floor_path` helper).  After drawing the combined fill patch,
redraw only the outer edge loop and then the void edge loops separately at their correct
line weights (layers 9 and 10 in the Z-order table).  This two-pass approach (fill then
re-stroke) guarantees line weights are applied correctly regardless of matplotlib's path
rendering order.

---

## 7. Scale Bar

Draw in the lower-left corner of the axes (data-space, not figure-space, so it scales with
zoom).  Anchor point: `(xlim[0] + margin * 0.3, ylim[0] + margin * 0.3)`.

Segments:
- One horizontal line of 5 m, divided into 5 × 1 m ticks, alternating black/white fill.
- Label "0" at left end, "5 m" at right end, "1:200" scale notation centered below.

Thickness: 0.8 pt line, 2.5 pt solid black/white alternating blocks drawn as filled rectangles
(`height = 0.4 m` in data units).

Only draw if `show_scale_bar=True` and the axes span is at least 6 m.

---

## 8. Multi-Floor Composition

### 8.1 Convenience Function

```python
def draw_floor_plan_grid(
    floors: list[FloorData],
    *,
    column_grid: ColumnGrid | None = None,
    original_footprint: list[tuple[float, float]] | None = None,
    n_cols: int = 3,
    subplot_size: float = 4.5,
    title: str | None = None,
    show_column_labels: bool = True,
    show_scale_bar: bool = True,
    show_north_arrow: bool = False,
    palette: dict | None = None,
    save_path: str | None = None,
) -> matplotlib.figure.Figure:
```

**Responsibility:** Create a figure, allocate subplots in a grid, call `draw_floor_plan`
once per floor, hide unused subplots, add a shared figure title, and optionally save.

**Layout rules:**
- `n_rows = ceil(len(floors) / n_cols)`.
- Each subplot is `subplot_size × subplot_size` inches.
- Figure size: `(n_cols * subplot_size, n_rows * subplot_size)`.
- `show_column_labels`, `show_scale_bar`, and `show_north_arrow` are forwarded to each
  `draw_floor_plan` call, but `show_north_arrow` defaults to only the first subplot
  (top-left) to avoid clutter.

**Returns:** The `Figure` object so the caller can do further customization or `plt.show()`.

### 8.2 Single-Floor Stand-Alone Usage

```python
fig, ax = plt.subplots(figsize=(8, 8))
draw_floor_plan(ax, mass.floors[2], column_grid=col_grid, show_north_arrow=True)
plt.tight_layout()
plt.show()
```

This is the intended pattern for inspecting one specific floor in detail.

---

## 9. File Layout

```
src/
└── models/
    └── wire_utils.py              # already exists — extract_wire_loops()

src/
└── visualization/
    ├── __init__.py                # re-exports draw_floor_plan, draw_floor_plan_grid
    ├── floor_plan.py              # draw_floor_plan() + draw_floor_plan_grid()
    ├── palette.py                 # DEFAULT_PALETTE dict + merge_palette()
    └── scale_bar.py               # draw_scale_bar() + draw_north_arrow() helpers

test/
└── userInteraction/
    └── test_individuum_viz.py     # existing script — update Figure 2 to call draw_floor_plan_grid()
```

`src/visualization/` is a **new package**.  All display code goes here; the `src/models/`
layer stays free of matplotlib imports.

---

## 10. Interaction with Existing Code

| Existing element | Change required |
|---|---|
| `test_individuum_viz.py` Figure 2 | Replace inline subplot loop with `draw_floor_plan_grid()` call |
| `src/models/wire_utils.py` | No change — `extract_wire_loops()` is reused as-is |
| `src/models/column_grid.py` | No change — `ColumnGrid` is passed in directly |
| `src/models/building_core.py` | No change — `BuildingCore.x_min/x_max/y_min/y_max` are used directly |
| `src/models/individuum.py` | No change — `Individuum.build()` pipeline unchanged |

The `Individuum.build()` method currently returns `(original_mass, subtracted_mass, config)`.
The `ColumnGrid` is constructed inside `build()` and is not returned.  To pass it to the
visualization layer the caller must reconstruct it from `IndividuumParams`:

```python
from models.column_grid import ColumnGrid
from models.span_mode import SpanMode

col_grid = ColumnGrid.create(
    subtracted_mass,
    SpanMode.FIXED_SPAN,
    span_x=params.span_x,
    span_y=params.span_y,
)
```

Alternatively, `Individuum.build()` could be extended to return a 4-tuple
`(original_mass, subtracted_mass, config, column_grid)` — this is the preferred long-term
change as it avoids reconstructing the grid with potentially different parameters.

---

## 11. Implementation Order

1. **`src/visualization/palette.py`** — define `DEFAULT_PALETTE` and `merge_palette()`.
2. **`src/visualization/scale_bar.py`** — `draw_scale_bar(ax, anchor, length_m, palette)` and
   `draw_north_arrow(ax, anchor, palette)`.
3. **`src/visualization/floor_plan.py`** — `draw_floor_plan()` and `draw_floor_plan_grid()`.
4. **`src/visualization/__init__.py`** — re-export public API.
5. **Update `test_individuum_viz.py`** — replace Figure 2 with `draw_floor_plan_grid()`.

---

## 12. Open Decisions

| Question | Recommendation |
|---|---|
| Should column grid be reconstructed by the caller or returned from `Individuum.build()`? | Return it from `build()` (preferred) — avoids silent parameter mismatch |
| Hatch pattern: matplotlib `hatch=` parameter or manually drawn lines? | Use matplotlib `hatch='////'` on `PathPatch`; simpler and consistent across backends |
| Should void boundaries show wall thickness? | Not in this phase — single-line boundary is sufficient at 1:200 scale |
| Column dot at out-of-footprint intersections? | Draw with 35 % alpha; useful for irregular polygons |
| Should `draw_floor_plan_grid` accept a custom axes array (for embedding in larger figures)? | Yes — add optional `axes: np.ndarray | None = None` parameter; if provided, skip figure creation |
| Dimension strings (e.g., span labels between grid lines)? | Defer to a future spec — adds significant complexity |
