# Individuum Generation — Requirements

_Based on Wang et al. (2019): "Subtractive Building Massing for Performance-Based Architectural
Design Exploration", Sustainability 11, 6965._

---

## 1. Algorithm Overview (Wang et al. 2019)

The paper proposes a **subtractive form generation** algorithm for building massing in evolutionary
optimization. Starting from a maximal solid volume, different parts are removed by rectangular
"subtractors", yielding topologically diverse building massings. These massings can represent
courtyards, atriums, stilts, cascaded roofs, and notches — all encoded in a compact, evolvable
genome.

### 1.1 Key Terms

| Term | Meaning |
|---|---|
| **Maximal volume** | Solid block defined by footprint polygon × floor height × num_floors |
| **Subtractor** | Axis-aligned box that is boolean-subtracted from the maximal volume |
| **Vertical subtractor** | Tall void spanning most of the building height → courtyards, atriums |
| **Horizontal subtractor** | Flat void spanning limited floors → stilts, empty floors, cascades |
| **Initialization parameters** | Fixed values set before optimization starts |
| **Optimization parameters** | The genome — varied by the EA during optimization |
| **Individuum** | One candidate design: genome + resulting geometry |

### 1.2 Initialization Parameters (fixed per run)

| Parameter | Type | Description |
|---|---|---|
| `polygon_points` | `list[tuple[float,float,float]]` | Footprint vertices in the XY plane |
| `floor_height` | `float` | Uniform height per floor (m) |
| `num_floors` | `int` | Total number of floors |
| `n_vertical` | `int` | Number of vertical subtractors |
| `n_horizontal` | `int` | Number of horizontal subtractors |
| `span_x` | `float` | Column grid spacing in X (m) |
| `span_y` | `float` | Column grid spacing in Y (m) |
| `min_plan_spans` | `float` | Min subtractor plan size in column spans (default 2) |
| `max_plan_spans` | `float` | Max subtractor plan size in column spans (default 5) |
| `boundary_constraint_enabled` | `bool` | True → enclosed voids; False → open notches |
| `boundary_snap_fraction` | `float` | Fraction within which a face snaps to the boundary (default 0.10) |
| `vertical_snap_threshold` | `float` | Fraction of total_height for top/bottom snap (default 0.30) |
| `horizontal_max_height_ratio` | `float` | Max height of horizontal subtractor as fraction of total_height (default 0.30) |

### 1.3 Optimization Parameters — Genome Encoding

Each individuum is encoded as a flat list of **normalized floats in [0, 1]**. There are
`(n_vertical + n_horizontal) × 6` genes in total.

For subtractor `k` (vertical subtractors first, then horizontal):

| Gene index | Symbol | Maps to |
|---|---|---|
| `k*6 + 0` | `x_norm` | `x = bbox_xmin + x_norm × bbox_width` |
| `k*6 + 1` | `y_norm` | `y = bbox_ymin + y_norm × bbox_depth` |
| `k*6 + 2` | `w_norm` | `width = w_norm × bbox_width` |
| `k*6 + 3` | `d_norm` | `depth = d_norm × bbox_depth` |
| `k*6 + 4` | `z_bot_norm` | `z_bottom = z_bot_norm × total_height` |
| `k*6 + 5` | `z_top_norm` | `z_top = z_top_norm × total_height` |

If `z_top < z_bottom`, they are swapped. If `z_top == z_bottom`, `z_top` is set to
`z_bottom + floor_height`.

Vertical subtractors occupy indices `k = 0 … n_vertical - 1`.
Horizontal subtractors occupy indices `k = n_vertical … n_vertical + n_horizontal - 1`.

---

## 2. Generation Pipeline

When `Individuum.build()` is called, it executes the following steps:

```
1. Create BuildingMass (maximal volume) from polygon_points, floor_height, num_floors
2. Create ColumnGrid from span_x, span_y
3. Decode genome → raw Subtractor objects (denormalized)
4. Align each subtractor to the nearest quarter-span position via ColumnGrid.align_subtractor()
   → subtractors that collapse to zero size are deactivated (None)
5. Build SubtractionConfig with aligned subtractors and constraint parameters
6. Apply subtractions via apply_subtractions(mass, config):
   a. Plan-size constraint: clip oversized; deactivate undersized (< min_plan_size)
   b. Vertical snap: snap z_bottom / z_top to 0 or total_height if within snap threshold;
      deactivate if neither face qualifies
   c. Horizontal height constraint: clip if > horizontal_max_height_ratio × total_height;
      deactivate if < floor_height
   d. Boundary constraint: clip inside (enabled) or snap outward through wall (disabled)
7. Return (original_mass, subtracted_mass, config)
```

---

## 3. Classes to Implement

### 3.1 `IndividuumParams`  (`src/models/individuum.py`)

Dataclass holding all initialization parameters (see table in §1.2).
Provides computed properties:
- `genome_length` → `(n_vertical + n_horizontal) * 6`
- `total_height` → `floor_height * num_floors`
- `bbox_width`, `bbox_depth`, `bbox_xmin`, `bbox_xmax`, `bbox_ymin`, `bbox_ymax` — footprint extents
- `min_plan_size`, `max_plan_size` — derived from span sizes and span limits

Validation:
- `floor_height > 0`
- `num_floors >= 1`
- `n_vertical >= 0`, `n_horizontal >= 0`
- `span_x > 0`, `span_y > 0`
- `min_plan_spans > 0`, `max_plan_spans >= min_plan_spans`

### 3.2 `Individuum`  (`src/models/individuum.py`)

Dataclass holding `params: IndividuumParams` and `genome: list[float]`.

| Method | Description |
|---|---|
| `__post_init__` | Validate genome length and that all genes ∈ [0, 1] |
| `create_random(params, rng)` | Class method — sample uniform [0, 1] for all genes |
| `_decode_subtractor(k, sub_type)` | Decode subtractor k from genome; returns raw `Subtractor` |
| `build()` | Full pipeline → returns `(original_mass, subtracted_mass, config)` |

---

## 4. Relationship to Existing Components

```
IndividuumParams ──► BuildingMass.create()        (maximal volume)
                └──► ColumnGrid.create()           (grid for alignment)

Individuum.genome ──► _decode_subtractor()         (denormalize genes)
                  └──► ColumnGrid.align_subtractor() (snap to quarter-span)
                      └──► SubtractionConfig          (wraps all constraints)
                          └──► apply_subtractions()   (boolean cuts + constraints)
                              └──► BuildingMass       (final cut geometry)
```

---

## 5. Visual Test

`test/userInteraction/test_individuum.py`

Creates a random individuum on a 20 × 20 m, 6-floor building with:
- 2 vertical subtractors (courtyards / notches)
- 2 horizontal subtractors (stilts / cascades)
- Column grid: 4 × 4 m spans

Displays:
- Original maximal volume (faint grey)
- Subtracted building mass (transparent white + cyan floor wires)
- Subtractor boxes (red wireframe, raw pre-alignment)
- Aligned subtractor boxes (orange wireframe, post-alignment)
