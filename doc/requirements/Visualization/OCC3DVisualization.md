# OCC 3D Visualization — Specification

## 1. Context & Motivation

The project currently has two separate approaches to 3D visualization:

| Approach | File | Strengths | Weaknesses |
|---|---|---|---|
| **OCC SimpleGui (Tkinter)** | `test_subtraction.py`, `test_individuum.py` | Real OpenGL, correct depth sorting, orbit/zoom/pan, good material rendering | Display code duplicated in every script; not modular |
| **matplotlib 3D** | `test_individuum_viz.py` Figure 1 | No extra dependencies, static PNG output | No real depth sorting, z-fighting on overlapping faces, flat unlit appearance |

The matplotlib 3D approach does not scale well — as the building geometry becomes more complex (voids, cores, ground plane) the rendering artifacts become visually distracting. The OCC SimpleGui viewer already produces better results and should become the primary 3D view.

This spec defines:

1. A **modular OCC visualization API** (`src/visualization/occ_scene.py`) that any script can call to add standard visual elements to an OCC display context.
2. An **isometric PNG export** from an OCC view — capturing the view to a PNG file in both interactive and headless mode.
3. An **architectural render mode** — white opaque building with cast shadows and ambient occlusion, plus a ground plane — using OCC's built-in ray-tracing pipeline.
4. A **headless rendering path** — produce a PNG without opening any window, suitable for batch generation and CI pipelines.

---

## 2. Feasibility Analysis

### 2.1 Modular OCC Display API

**Feasible.** The current display pattern (create `AIS_Shape`, set `Prs3d_ShadingAspect`, call `context.Display`) is already working in every test script. Extracting these patterns into named functions is pure refactoring — no new OCC APIs required.

### 2.2 Isometric PNG Export from OCC View

**Feasible — in both interactive and headless mode.**

`V3d_View.Dump(filename)` writes the current OpenGL framebuffer contents to a PNG file.  It works when the OpenGL context has rendered at least one frame.

Two operating modes are supported (see Section 2.4 for headless details):

| Mode | How triggered | Window shown |
|---|---|---|
| **Interactive + save** | `--save path.png` flag; Tk `after(300ms)` callback writes PNG then viewer stays open | Yes |
| **Headless** | `--headless` flag; OCC offscreen context, no window | No |

For the interactive save path:
```python
def _export_and_continue(save_path: str) -> None:
    display.View.Dump(save_path)

# Before start_display():
if args.save:
    display._window.canvas._canvas.after(
        300, lambda: _export_and_continue(args.save)
    )
```

### 2.3 Architectural Render Mode (Shadows + Ground Plane)

### 2.3 Architectural Render Mode (Shadows + Ground Plane)

**Fully feasible within OCC.** No additional software is needed.


OCC 7.4+ ships a built-in ray-tracing renderer (`Graphic3d_RM_RAYTRACING`) accessible from pythonocc. It supports:

| Feature | OCC API | Notes |
|---|---|---|
| Ray-tracing | `Graphic3d_RenderingParams.Method = Graphic3d_RM_RAYTRACING` | OpenGL 4 required |
| Hard shadows | `IsShadowEnabled = True` | Directional light shadows |
| Ambient occlusion | `IsAmbientOcclusionEnabled = True` | Softens corners |
| Reflections | `IsReflectionEnabled = True` | Subtle metallic look |
| Trace depth | `RaytracingDepth = 3` | 1–10; higher = slower |

Material setup for the architectural render:

```python
from OCC.Core.Graphic3d import Graphic3d_MaterialAspect, Graphic3d_NOM_PLASTER
mat = Graphic3d_MaterialAspect(Graphic3d_NOM_PLASTER)
mat.SetColor(Quantity_Color(Quantity_NOC_WHITE))
```

`Graphic3d_NOM_PLASTER` is a matte, diffuse-only material — ideal for the white architectural model look where only shadows carry information.

Ground plane: a thin flat box at z = 0 (or a planar face), styled with the same white plaster material.

Directional light: OCC's default light is a headlight that follows the camera. For shadows the light must be positioned independently:

```python
from OCC.Core.V3d import V3d_DirectionalLight
from OCC.Core.gp import gp_Dir
light = V3d_DirectionalLight(
    display.Viewer,
    gp_Dir(1.0, -0.8, -1.5),   # roughly NW-top → SE-bottom
    True,                        # head_light=False equivalent
)
display.Viewer.AddLight(light)
display.Viewer.SetLightOn(light)
display.View.SetLightOn()
```

The subtracted voids (courtyards, stilts) will cast and receive shadows automatically because the boolean-cut geometry is a physically accurate solid — OCC's ray tracer sees the actual geometry, not just a visual approximation.

---

### 2.4 Headless PNG Rendering

**Feasible.** Two approaches are available, with different trade-offs:

---

#### Approach A — Xvfb (Virtual Framebuffer)

Run an invisible X11 server in software. The existing `init_display()` code works completely unchanged.

```bash
# Start virtual display once per session (or in a script wrapper)
Xvfb :99 -screen 0 1920x1080x24 &
DISPLAY=:99 python test/userInteraction/test_individuum_viz.py --save /tmp/render.png
```

| Pro | Con |
|---|---|
| Zero code changes | Requires `Xvfb` to be installed (`apt install xvfb`) |
| Ray-tracing works if GPU driver supports EGL | GPU acceleration depends on driver; may fall back to software Mesa |
| Works on any Linux workstation or CI with `Xvfb` | An extra background process to manage |

This is the **recommended quick-start approach**. A small shell wrapper `scripts/render_headless.sh` can handle the Xvfb lifecycle automatically.

---

#### Approach B — OCC Offscreen Context (no X11 required)

OCC 7.4+ supports rendering into an offscreen pixmap via `Aspect_NeutralWindow` + `OpenGl_GraphicDriver`. No X11, no window manager, no `DISPLAY` variable needed. Works inside Docker containers and SSH sessions.

```python
from OCC.Core.Aspect import Aspect_NeutralWindow
from OCC.Core.OpenGl import OpenGl_GraphicDriver
from OCC.Core.V3d import V3d_Viewer
from OCC.Core.Image import Image_AlienPixMap

# Create an offscreen OpenGL context
graphic_driver = OpenGl_GraphicDriver(Aspect_NeutralWindow())
viewer = V3d_Viewer(graphic_driver)
view = viewer.CreateView()

offscreen_window = Aspect_NeutralWindow()
offscreen_window.SetSize(1920, 1080)
view.SetWindow(offscreen_window)
offscreen_window.Map()

# ... add shapes to AIS context, fit view, set camera ...

# Render to pixmap
pixmap = Image_AlienPixMap()
pixmap.InitZero(Image_AlienPixMap.ImgBGRA, 1920, 1080)
view.ToPixMap(pixmap, 1920, 1080)
pixmap.Save("/path/to/output.png")
```

| Pro | Con |
|---|---|
| No X11, no system-level dependencies | More boilerplate — does not use `init_display()` |
| Runs in Docker / CI without any display server | `Aspect_NeutralWindow` is an internal OCC API; may need GPU driver with EGL support |
| Can render at arbitrary resolution (e.g. 4K for print) | Ray-tracing requires EGL or Mesa GLSL; confirm GPU driver supports it |

---

#### Chosen API design

The `occ_scene` module exposes a single `render_png` function that abstracts both approaches behind a `headless` flag:

```python
def render_png(
    mass: BuildingMass,
    path: str,
    *,
    style: str = "ARCHITECTURAL",   # "DIAGNOSTIC" | "ARCHITECTURAL"
    headless: bool = False,          # True → offscreen; False → interactive window + Dump
    width: int = 1920,
    height: int = 1080,
    config: SubtractionConfig | None = None,
    show_original: bool = False,
) -> None:
    """
    Render a building mass to a PNG file.

    headless=False  Opens an OCC viewer window, sets the camera to isometric,
                    waits 300 ms for the first frame, writes the PNG via
                    V3d_View.Dump, then keeps the viewer open.

    headless=True   Creates an Aspect_NeutralWindow offscreen context, renders
                    to Image_AlienPixMap, and saves without opening any window.
                    Suitable for batch generation and CI pipelines.
    """
```

Scripts continue to use `init_display()` directly for fully interactive sessions (orbit, zoom, pick). `render_png` is the entry point only when a PNG output is the goal.

---

#### Recommendation per use case

| Use case | Recommended approach |
|---|---|
| Daily interactive inspection on workstation | `init_display()` + `start_display()` — no PNG needed |
| Quick snapshot during interactive session | `--save path.png` flag (interactive + Tk callback) |
| Batch render of many individua in a script | `render_png(..., headless=True)` |
| CI pipeline / server without GPU | `render_png(..., headless=True)` + Mesa software renderer |
| High-res print-quality render | `render_png(..., headless=True, width=3840, height=2160)` |

---

## 3. Interactive Viewer Design (OCC SimpleGui)

### 3.1 Visual Style Vocabulary

Two named styles cover all current use cases:

| Style name | Purpose | Material | Transparency |
|---|---|---|---|
| `DIAGNOSTIC` | Debug view — shows all elements with distinct colours, semi-transparent to reveal inner structure | Phong shading, per-element colour | 0.7–0.95 for volumes; 0 for wires |
| `ARCHITECTURAL` | Presentation render — uniform white, ray-traced shadows, ground plane | Plaster (matte diffuse), white | 0 (fully opaque) |

### 3.2 Standard Visual Elements

Each element below maps to a function in `src/visualization/occ_scene.py`:

| Function | Renders | Default style |
|---|---|---|
| `add_building_mass(context, mass, style)` | Floor solids + polygon wires | `DIAGNOSTIC`: semi-transparent white + coloured floor wires |
| `add_original_mass(context, mass)` | Original (uncut) floor solids | Ghost silhouette: very faint grey, dot-line edges |
| `add_subtractors(context, config, style)` | Subtractor boxes | `DIAGNOSTIC`: red wireframe (raw) or orange wireframe (aligned) |
| `add_cores(context, mass)` | Core boxes spanning full height | Semi-transparent blue |
| `add_ground_plane(context, mass, padding)` | Flat slab at z = 0 extending `padding` m beyond the footprint bbox | White matte |
| `configure_isometric_view(display)` | Camera position only | `elev=35.264°, azim=45°` (true isometric) |
| `configure_ray_tracing(display)` | Enable ray-tracing + shadows + AO | Modifies `Graphic3d_RenderingParams` |
| `export_png(display, path)` | Write current framebuffer to PNG | Calls `display.View.Dump(path)` |

### 3.3 Background

| Mode | Background |
|---|---|
| `DIAGNOSTIC` | Very dark navy gradient `[8, 8, 25]` — current convention; high contrast for bright wires |
| `ARCHITECTURAL` | Light grey or white gradient `[230, 235, 240]` — matches white model aesthetic |

---

## 4. Diagnostic Render (Style 1)

Replaces and generalises the current code in every test script.

### Visual elements

| Element | Colour | Transparency | Line style |
|---|---|---|---|
| Original mass floor solids | `GRAY60` | 0.97 | Dot-line edges |
| Subtracted mass floor solids | White | 0.82 | Dot-line edges |
| Subtracted mass floor wires | Cyan `(0.2, 0.9, 0.9)` | 0 | Solid 2.0 pt |
| Raw subtractor boxes | Red | 1.0 (wireframe only) | Solid 1.5 pt |
| Aligned subtractor boxes | Orange | 1.0 (wireframe only) | Solid 2.0 pt |
| Building core boxes | Blue `(0.15, 0.45, 1.0)` | 0.55 | Solid 2.0 pt |

This matches the existing style exactly — the modular API just wraps it.

### Isometric PNG export

After all shapes are added and `display.FitAll()` is called, the script can export:

```python
configure_isometric_view(display)
# Schedule Dump 300 ms after event loop starts
display._window.canvas._canvas.after(300, lambda: export_png(display, path))
start_display()
```

---

## 5. Architectural Render (Style 2)

### Visual elements

| Element | Material | Colour | Transparency |
|---|---|---|---|
| Building mass (subtracted) | `Graphic3d_NOM_PLASTER` | White `#ffffff` | 0 (fully opaque) |
| Building cores | `Graphic3d_NOM_PLASTER` | Light grey `#d0d8e0` | 0 |
| Ground plane | `Graphic3d_NOM_PLASTER` | White `#ffffff` | 0 |
| Background gradient | — | `[230, 235, 240]` → `[255, 255, 255]` | — |

The original mass is **not shown** in this mode — only the final subtracted geometry.
Floor wires, subtractor boxes, and diagnostic colours are also **not shown**.

### Lighting setup

A single directional light from the upper-left-front (approx. northwest sun at 45° elevation) produces clean cast shadows that reveal the voids:

```
Light direction vector: (1.0, -0.8, -1.5)  (points toward origin)
Ambient component: low (0.15) — keeps shadows readable without crushing darks
```

The ground plane catches shadows from the building, making stilts and overhangs visible from above.

### Ray-tracing parameters

```python
params = display.View.RenderingParams()
params.Method                   = Graphic3d_RM_RAYTRACING
params.IsShadowEnabled          = True
params.IsAmbientOcclusionEnabled = True
params.IsReflectionEnabled      = False   # keep it matte
params.RaytracingDepth          = 3
display.View.ChangeRenderingParams(params)
```

### Ground plane geometry

```python
padding = max(bbox_width, bbox_depth) * 0.4
ground = BRepPrimAPI_MakeBox(
    gp_Pnt(-padding,          -padding,          -0.05),
    gp_Pnt(bbox_width+padding, bbox_depth+padding, 0.0),
).Shape()
```

Height −0.05 to 0.0 m (5 cm thin) so the base of the building sits cleanly on its surface.

---

## 6. Modular API — `src/visualization/occ_scene.py`

```python
# Public API

def add_building_mass(
    context,
    mass: BuildingMass,
    *,
    style: str = "DIAGNOSTIC",        # "DIAGNOSTIC" | "ARCHITECTURAL"
    show_floor_wires: bool = True,     # DIAGNOSTIC only
) -> list:
    """Add all floor solids (and wires) to the AIS context. Returns AIS objects."""

def add_original_mass(
    context,
    mass: BuildingMass,
) -> list:
    """Add the uncut original mass as a faint ghost silhouette."""

def add_subtractors(
    context,
    config: SubtractionConfig,
    *,
    raw: list | None = None,           # pre-alignment subtractors (red)
    aligned_only: bool = False,        # show only aligned (orange)
) -> list:

def add_cores(
    context,
    mass: BuildingMass,
) -> list:

def add_ground_plane(
    context,
    mass: BuildingMass,
    *,
    padding_factor: float = 0.4,
) -> list:

def configure_diagnostic_background(display) -> None:
    """Dark navy gradient [8, 8, 25]."""

def configure_architectural_background(display) -> None:
    """Light grey-to-white gradient."""

def configure_isometric_view(display) -> None:
    """Set camera to true isometric (elev=35.264°, azim=45°) and FitAll."""

def configure_ray_tracing(display) -> None:
    """Enable Graphic3d_RM_RAYTRACING with shadows and ambient occlusion."""

def export_png(display, path: str, delay_ms: int = 300) -> None:
    """
    Schedule a Dump of the current view to *path* via a Tk `after` callback.

    The delay allows the event loop to complete at least one render cycle
    before the framebuffer is captured.  The viewer remains open after export.
    Only valid when using the interactive (SimpleGui) display.
    """

# ── High-level convenience entry point ────────────────────────────────────────

def render_png(
    mass: "BuildingMass",
    path: str,
    *,
    style: str = "ARCHITECTURAL",
    headless: bool = False,
    width: int = 1920,
    height: int = 1080,
    config: "SubtractionConfig | None" = None,
    show_original: bool = False,
) -> None:
    """
    Render a building mass to a PNG without manual viewer setup.

    headless=False  Opens an OCC SimpleGui window, sets isometric camera,
                    exports PNG via Tk callback, keeps viewer open.
    headless=True   Uses Aspect_NeutralWindow offscreen context + ToPixMap.
                    No window is shown. Suitable for batch and CI use.
    """
```

`add_*` functions return a list of `AIS_Shape` objects so the caller can selectively show/hide elements later.  `render_png` is the single-call entry point when only a PNG output is needed.

---

## 7. File Layout

```
src/
└── visualization/
    ├── __init__.py           # existing — add occ_scene exports
    ├── palette.py            # existing
    ├── scale_bar.py          # existing
    ├── floor_plan.py         # existing
    └── occ_scene.py          # NEW — modular OCC display helpers

test/
└── userInteraction/
    ├── test_subtraction.py       # update: use occ_scene API
    ├── test_individuum.py        # update: use occ_scene API
    ├── test_individuum_viz.py    # update: Figure 1 replaced by OCC scene, or removed
    └── test_building_core.py     # update: use occ_scene API
```

The matplotlib isometric (Figure 1 in `test_individuum_viz.py`) should be **replaced** by the OCC ARCHITECTURAL render once this feature is implemented, since the OCC render is visually superior. Figure 1 can be removed or kept as a lightweight fallback for environments without OpenGL.

---

## 8. Implementation Order

1. **`src/visualization/occ_scene.py`** — implement `add_building_mass` + `add_original_mass` + `add_subtractors` + `add_cores` with DIAGNOSTIC style only. Verify by updating `test_subtraction.py`.
2. **`export_png`** — add and verify the Tk-after export in `test_subtraction.py --save`.
3. **`configure_isometric_view`** — set camera and test PNG output looks correct.
4. **`add_ground_plane` + `configure_ray_tracing` + ARCHITECTURAL style** — architectural render mode. Verify with `test_individuum.py`.
5. **Update all test scripts** to use the new API.
6. **Replace matplotlib Figure 1** in `test_individuum_viz.py` with OCC ARCHITECTURAL render PNG.

---

## 9. Open Decisions

| Question | Recommendation |
|---|---|
| Should `export_png` keep the viewer open or close it after saving? | Keep open by default; `render_png(headless=False)` keeps it open; `headless=True` has no window to close |
| Should ARCHITECTURAL render be a separate script or a `--mode` flag? | `--mode diagnostic\|architectural` flag on test scripts; `render_png` handles both via `style=` |
| Ray-tracing requires OpenGL 4 — what if the GPU only supports OpenGL 3? | Fall back to Phong shading; detect at runtime via `glGetString(GL_VERSION)` and print a warning |
| Should `configure_ray_tracing` be called before or after `start_display()`? | Must be called BEFORE `start_display()` — rendering parameters are set at context creation |
| Ground plane: flat box or infinite plane (AIS_Plane)? | Flat box — easier to style and export; `AIS_Plane` has no fill material in OCC |
| Should cores use the ARCHITECTURAL material or a slightly different shade? | Slightly off-white (`#d0d8e0`) to make cores visually distinct without colour |
| Headless: Xvfb wrapper or `Aspect_NeutralWindow` offscreen context? | Both are supported; start with Xvfb (zero code change) and add offscreen context later for CI use |
| Output resolution for headless? | Default 1920×1080; pass `width`/`height` to `render_png` for print-quality export |
