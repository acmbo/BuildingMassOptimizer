# pythonocc-core 7.9.3 — Findings & Gotchas

Environment: Python 3.13, pythonocc-core 7.9.3, Conda env `pyoccEnv`.

---

## 1. BRep Topology Model

OCC represents all geometry as **Boundary Representation (BRep)**:

```
Solid → Shell → Face → Wire → Edge → Vertex
```

All shapes are instances of `TopoDS_Shape` (or its typed subclasses).
Shapes are **immutable** — operations return new shapes.

---

## 2. Shape Casting

### Problem: `topods_Edge` removed in 7.9.x

Older pythonocc code uses a module-level cast function:

```python
from OCC.Core.TopoDS import topods_Edge   # BROKEN in 7.9.x — ImportError
```

### Fix: use the lowercase free function `Edge`

```python
from OCC.Core.TopoDS import Edge as topods_Edge
edge = topods_Edge(explorer.Current())
```

Note: `TopoDS_Edge(shape)` (class constructor) does **not** accept a shape
argument — it only constructs an empty edge:

```python
TopoDS_Edge(some_shape)   # TypeError: takes no arguments
```

The same pattern applies to other shape types (`Face`, `Wire`, `Shell`, etc.):

```python
from OCC.Core.TopoDS import Face as topods_Face
from OCC.Core.TopoDS import Wire as topods_Wire
```

---

## 3. Edge Vertex / Endpoint Extraction

### Deprecated functions (still work, but print warnings)

```python
from OCC.Core.TopExp import topexp_FirstVertex, topexp_LastVertex
from OCC.Core.BRep import BRep_Tool

v1 = topexp_FirstVertex(edge)    # DeprecationWarning since 7.7.1
v2 = topexp_LastVertex(edge)
p1 = BRep_Tool.Pnt(v1)
p2 = BRep_Tool.Pnt(v2)
```

The deprecation message says "use the static method `topexp.FirstVertex`"
but **no such module exists** in 7.9.3 — `OCC.Core.topexp` raises
`ModuleNotFoundError`.

### Fix: use `BRepAdaptor_Curve` (no warnings, clean API)

```python
from OCC.Core.BRepAdaptor import BRepAdaptor_Curve

curve = BRepAdaptor_Curve(edge)
p1 = curve.Value(curve.FirstParameter())
p2 = curve.Value(curve.LastParameter())
```

`Value(t)` returns a `gp_Pnt` directly.  This works for any curve type
(line, arc, spline) and does not trigger any deprecation warnings.

---

## 4. Topology Traversal

### `TopExp_Explorer`

```python
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_WIRE

explorer = TopExp_Explorer(shape, TopAbs_EDGE)
while explorer.More():
    edge = topods_Edge(explorer.Current())
    # ... process edge ...
    explorer.Next()
```

Works on any shape type (Wire, Face, Solid, Compound).  For a compound of
wires (e.g. after boolean subtraction), it traverses all edges across all
sub-shapes automatically.

---

## 5. AABB Computation

```python
from OCC.Core.Bnd import Bnd_Box
from OCC.Core import brepbndlib

bbox = Bnd_Box()
brepbndlib.Add(shape, bbox)
xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
```

**Important:** `brepbndlib` adds a small tolerance gap (~1e-7 m) around the
shape.  The returned AABB is slightly larger than the raw polygon coordinates.
Do not use it for exact dimension checks — compare with `math.isclose` or a
tolerance band.

---

## 6. Boolean Cut

```python
from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut

cut = BRepAlgoAPI_Cut(base_solid, tool_solid)
if not cut.IsDone():
    raise RuntimeError("Boolean cut failed")

result = cut.Shape()
```

Validation after cut (checks for degenerate geometry):

```python
from OCC.Core.BRepCheck import BRepCheck_Analyzer

analyzer = BRepCheck_Analyzer(result)
if not analyzer.IsValid():
    # shape has geometric errors — handle or skip
    pass
```

Both operands must be **solids** (`BRepPrimAPI_MakePrism`, `BRepPrimAPI_MakeBox`, etc.).

---

## 7. Geometry Primitives

### Box (axis-aligned)

```python
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.gp import gp_Pnt

box = BRepPrimAPI_MakeBox(gp_Pnt(x0, y0, z0), gp_Pnt(x1, y1, z1)).Shape()
```

### Polygon wire → solid extrusion

```python
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCC.Core.gp import gp_Pnt, gp_Vec

poly = BRepBuilderAPI_MakePolygon()
for x, y, z in points:
    poly.Add(gp_Pnt(x, y, z))
poly.Close()
wire = poly.Wire()

face = BRepBuilderAPI_MakeFace(wire).Face()
solid = BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, height)).Shape()
```

### Translation

```python
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCC.Core.gp import gp_Trsf, gp_Vec

trsf = gp_Trsf()
trsf.SetTranslation(gp_Vec(0, 0, dz))
moved = BRepBuilderAPI_Transform(shape, trsf, True).Shape()
```

---

## 8. Compound Builder

Combine multiple shapes into a single compound (e.g. a collection of wires):

```python
from OCC.Core.BRep import BRep_Builder
from OCC.Core.TopoDS import TopoDS_Compound

builder = BRep_Builder()
compound = TopoDS_Compound()
builder.MakeCompound(compound)
builder.Add(compound, shape_a)
builder.Add(compound, shape_b)
```

---

## 9. OCC Viewer (SimpleGui)

```python
from OCC.Display.SimpleGui import init_display

display, start_display, add_menu, add_function_to_menu = init_display()
```

### Shape display with custom colour and transparency

```python
from OCC.Core.AIS import AIS_Shape
from OCC.Core.Prs3d import Prs3d_ShadingAspect, Prs3d_LineAspect
from OCC.Core.Aspect import Aspect_TOL_SOLID, Aspect_TOL_DOT
from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB

ais = AIS_Shape(shape)
drawer = ais.Attributes()

shading = Prs3d_ShadingAspect()
shading.SetColor(Quantity_Color(r, g, b, Quantity_TOC_RGB))
shading.SetTransparency(0.7)          # 0.0 = opaque, 1.0 = invisible
drawer.SetShadingAspect(shading)

edge_aspect = Prs3d_LineAspect(color, Aspect_TOL_SOLID, line_width)
drawer.SetWireAspect(edge_aspect)
drawer.SetFaceBoundaryAspect(edge_aspect)
drawer.SetFaceBoundaryDraw(True)

context = display.Context
context.Display(ais, False)
context.SetDisplayMode(ais, 1, False)  # 1 = shaded
```

### Named colours

```python
from OCC.Core.Quantity import (
    Quantity_NOC_WHITE, Quantity_NOC_RED, Quantity_NOC_GRAY60,
    Quantity_NOC_CYAN1, Quantity_NOC_BLUE1,
)
color = Quantity_Color(Quantity_NOC_WHITE)
```

### Background colour

```python
display.set_bg_gradient_color([8, 8, 25], [8, 8, 25])  # dark navy
```

---

## 10. Coordinate System

OCC uses a **right-handed** coordinate system:

- **X** → width (East)
- **Y** → depth (North)
- **Z** → height (up)

Floor polygons are defined in the XY plane (`z = 0`) and extruded along +Z.

---

## 11. Module Index

| Module | Key classes / functions | Purpose |
|---|---|---|
| `OCC.Core.gp` | `gp_Pnt`, `gp_Vec`, `gp_Trsf` | Geometric primitives |
| `OCC.Core.TopoDS` | `TopoDS_Shape`, `Edge`, `Face`, `Wire`, `Compound` | Shape types + cast functions |
| `OCC.Core.TopAbs` | `TopAbs_EDGE`, `TopAbs_FACE`, `TopAbs_WIRE`, … | Shape-type enum constants |
| `OCC.Core.TopExp` | `TopExp_Explorer` | Topology traversal |
| `OCC.Core.BRep` | `BRep_Tool`, `BRep_Builder` | Low-level shape data access |
| `OCC.Core.BRepBuilderAPI` | `MakePolygon`, `MakeFace`, `MakeWire`, `Transform` | Shape construction |
| `OCC.Core.BRepPrimAPI` | `MakePrism`, `MakeBox` | Primitive solid creation |
| `OCC.Core.BRepAlgoAPI` | `BRepAlgoAPI_Cut`, `_Fuse`, `_Common` | Boolean operations |
| `OCC.Core.BRepAdaptor` | `BRepAdaptor_Curve` | Parameterised curve access on edges |
| `OCC.Core.BRepCheck` | `BRepCheck_Analyzer` | Shape validity after booleans |
| `OCC.Core.Bnd` + `brepbndlib` | `Bnd_Box`, `brepbndlib.Add` | AABB computation |
| `OCC.Core.AIS` | `AIS_Shape` | Interactive shape display |
| `OCC.Core.Prs3d` | `Prs3d_ShadingAspect`, `Prs3d_LineAspect` | Display attributes |
| `OCC.Core.Quantity` | `Quantity_Color`, `Quantity_NOC_*` | Colours |
| `OCC.Core.Aspect` | `Aspect_TOL_SOLID`, `Aspect_TOL_DOT` | Line type constants |
| `OCC.Display.SimpleGui` | `init_display` | Viewer window (Tkinter backend) |
