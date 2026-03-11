"""
PyVista 3D scene building helpers for BuildingMassOptimizer.

Mirrors the public API of ``occ_scene.py`` but uses PyVista / VTK instead of
the OCC interactive viewer.  Offscreen rendering works out-of-the-box (no
Xvfb required) thanks to VTK's EGL / OSMesa backend.

Public API
----------
add_building_mass(plotter, mass, *, style, show_floor_wires) -> list
    Add floor solids (and edge overlays) to the plotter.

add_original_mass(plotter, mass) -> list
    Add the uncut original mass as a faint ghost wireframe.

add_subtractors(plotter, config, *, raw, aligned_only) -> list
    Add subtractor boxes: raw in red wireframe, aligned in orange wireframe.

add_cores(plotter, mass) -> list
    Add building core boxes spanning full height.

add_ground_plane(plotter, mass, *, padding_factor, style) -> list
    Add a flat ground slab at z=0, extending beyond the building footprint.

configure_diagnostic_background(plotter) -> None
    Dark navy background, high contrast for bright wires.

configure_architectural_background(plotter) -> None
    Pure white background.

configure_isometric_view(plotter) -> None
    Set camera to isometric direction matching the OCC view (1.2, 0.8, 1.0).

render_png(mass, path, *, style, width, height, config, raw_subtractors,
           show_original, original_mass, interactive) -> None
    High-level convenience: build scene and export PNG (or open window).

Visual styles
-------------
DIAGNOSTIC
    Dark navy background, semi-transparent white building, cyan edge lines,
    red wireframe for raw subtractors, orange for aligned, blue cores.

ARCHITECTURAL
    White background, fully opaque light-grey building, white ground plane,
    no edge lines, no subtractor boxes, no ghost.
"""

from __future__ import annotations

import numpy as np
import pyvista as pv
from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
from OCC.Core.BRep import BRep_Tool
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE
from OCC.Core.TopoDS import topods
from OCC.Core.TopLoc import TopLoc_Location


# ── Colour constants (RGB 0–1) ─────────────────────────────────────────────────

_WHITE      = (0.95, 0.95, 0.95)
_ARCH_WHITE = (0.92, 0.92, 0.92)
_GRAY       = (0.60, 0.60, 0.60)
_CYAN       = (0.20, 0.90, 0.90)
_ORANGE     = (1.00, 0.55, 0.10)
_RED        = (1.00, 0.20, 0.20)
_BLUE       = (0.15, 0.45, 1.00)
_NAVY_BG    = (0.031, 0.031, 0.098)
_LIGHT_GRAY = (0.95, 0.95, 0.95)


# ── Geometry conversion ────────────────────────────────────────────────────────

def occ_shape_to_pyvista(shape, deflection: float = 0.05) -> pv.PolyData:
    """
    Tessellate an OCC BRep shape and return a :class:`pyvista.PolyData` mesh.

    Parameters
    ----------
    shape
        Any ``TopoDS_Shape`` — solid, shell, compound, etc.
    deflection
        Linear deflection for the incremental mesh.  Smaller values give a
        finer mesh at the cost of more triangles.  0.05 m is appropriate for
        building-scale geometry (≈ 5 cm chord error).

    Returns
    -------
    pyvista.PolyData
        Triangle mesh in world coordinates.  Returns an empty PolyData if the
        shape has no tessellatable faces (e.g. null shapes or wire-only).
    """
    BRepMesh_IncrementalMesh(shape, deflection).Perform()

    all_vertices: list[list[float]] = []
    all_faces: list[int] = []
    offset = 0

    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = topods.Face(exp.Current())
        loc = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation(face, loc)
        if triangulation is not None:
            n_nodes = triangulation.NbNodes()
            n_triangles = triangulation.NbTriangles()

            for i in range(1, n_nodes + 1):
                node = triangulation.Node(i)
                all_vertices.append([node.X(), node.Y(), node.Z()])

            for i in range(1, n_triangles + 1):
                tri = triangulation.Triangle(i)
                n1, n2, n3 = tri.Get()
                all_faces.extend([3, n1 - 1 + offset, n2 - 1 + offset, n3 - 1 + offset])

            offset += n_nodes
        exp.Next()

    if not all_vertices:
        return pv.PolyData()

    vertices = np.array(all_vertices, dtype=float)
    faces = np.array(all_faces, dtype=int)
    return pv.PolyData(vertices, faces)


def _box_mesh(xmin, xmax, ymin, ymax, zmin, zmax) -> pv.PolyData:
    """Axis-aligned box as a pyvista PolyData."""
    return pv.Box(bounds=(xmin, xmax, ymin, ymax, zmin, zmax))


# ── Public: add elements to plotter ───────────────────────────────────────────

def add_building_mass(
    plotter: pv.Plotter,
    mass,
    *,
    style: str = "DIAGNOSTIC",
    show_floor_wires: bool = True,
) -> list:
    """
    Add all floor solids to the plotter.

    Parameters
    ----------
    plotter
        :class:`pyvista.Plotter` instance.
    mass
        ``BuildingMass`` with ``.floors``.
    style
        ``"DIAGNOSTIC"`` — semi-transparent white + cyan edges (default).
        ``"ARCHITECTURAL"`` — opaque light-grey, no edge lines.
    show_floor_wires
        Ignored in ARCHITECTURAL style.  In DIAGNOSTIC mode, when True the
        mesh edges are drawn in cyan.

    Returns
    -------
    list of PyVista actor references.
    """
    result = []
    if style == "ARCHITECTURAL":
        for floor in mass.floors:
            mesh = occ_shape_to_pyvista(floor.solid)
            actor = plotter.add_mesh(
                mesh,
                color=_ARCH_WHITE,
                smooth_shading=True,
                show_edges=False,
            )
            result.append(actor)
    else:
        edge_color = _CYAN if show_floor_wires else _WHITE
        for floor in mass.floors:
            mesh = occ_shape_to_pyvista(floor.solid)
            actor = plotter.add_mesh(
                mesh,
                color=_WHITE,
                opacity=0.18,          # OCC transparency 0.82 → pyvista opacity 0.18
                show_edges=show_floor_wires,
                edge_color=edge_color,
                line_width=1.5,
                smooth_shading=True,
            )
            result.append(actor)
    return result


def add_original_mass(plotter: pv.Plotter, mass) -> list:
    """
    Add the uncut original mass as a faint ghost wireframe.

    Rendered at 3 % opacity (matching OCC transparency 0.97) in grey.
    """
    result = []
    for floor in mass.floors:
        mesh = occ_shape_to_pyvista(floor.solid)
        actor = plotter.add_mesh(
            mesh,
            color=_GRAY,
            opacity=0.03,
            style="wireframe",
            line_width=0.5,
        )
        result.append(actor)
    return result


def add_subtractors(
    plotter: pv.Plotter,
    config,
    *,
    raw: list | None = None,
    aligned_only: bool = False,
) -> list:
    """
    Add subtractor wireframe boxes to the plotter.

    Parameters
    ----------
    plotter
        :class:`pyvista.Plotter` instance.
    config
        ``SubtractionConfig`` — aligned subtractors drawn in **orange**.
        Pass ``None`` to skip aligned boxes.
    raw
        List of pre-alignment ``Subtractor`` objects drawn in **red**.
        Ignored when ``aligned_only=True``.
    aligned_only
        When True, skip the raw (red) boxes even if ``raw`` is provided.
    """
    result = []
    if raw is not None and not aligned_only:
        for sub in raw:
            box = _box_mesh(sub.x, sub.x + sub.width, sub.y, sub.y + sub.depth, sub.z_bottom, sub.z_top)
            actor = plotter.add_mesh(box, color=_RED, style="wireframe", line_width=1.5)
            result.append(actor)
    if config is not None:
        aligned = config.vertical_subtractors + config.horizontal_subtractors
        for sub in aligned:
            box = _box_mesh(sub.x, sub.x + sub.width, sub.y, sub.y + sub.depth, sub.z_bottom, sub.z_top)
            actor = plotter.add_mesh(box, color=_ORANGE, style="wireframe", line_width=2.0)
            result.append(actor)
    return result


def add_cores(plotter: pv.Plotter, mass) -> list:
    """
    Add building core boxes to the plotter.

    Each core is extruded from z=0 to ``mass.total_height`` as a
    semi-transparent blue solid (45 % opacity, matching OCC transparency 0.55).
    """
    result = []
    cores = getattr(mass, "cores", None) or []
    for core in cores:
        box = _box_mesh(core.x_min, core.x_max, core.y_min, core.y_max, 0.0, mass.total_height)
        actor = plotter.add_mesh(
            box,
            color=_BLUE,
            opacity=0.45,
            smooth_shading=True,
            show_edges=True,
            edge_color=_BLUE,
            line_width=1.5,
        )
        result.append(actor)
    return result


def add_ground_plane(
    plotter: pv.Plotter,
    mass,
    *,
    padding_factor: float = 0.4,
    style: str = "ARCHITECTURAL",
) -> list:
    """
    Add a thin flat ground slab at z=0 extending beyond the building footprint.

    Parameters
    ----------
    padding_factor
        Fraction of max(bbox_width, bbox_depth) added as margin on all sides.
    style
        ``"ARCHITECTURAL"`` → opaque white.
        ``"DIAGNOSTIC"`` → light grey, 70 % opacity.
    """
    xs = [p[0] for p in mass.polygon_points]
    ys = [p[1] for p in mass.polygon_points]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    pad = max(xmax - xmin, ymax - ymin) * padding_factor
    ground = _box_mesh(xmin - pad, xmax + pad, ymin - pad, ymax + pad, -0.05, 0.0)
    if style == "ARCHITECTURAL":
        actor = plotter.add_mesh(ground, color=(1.0, 1.0, 1.0), smooth_shading=True, show_edges=False)
    else:
        actor = plotter.add_mesh(ground, color=_LIGHT_GRAY, opacity=0.70, show_edges=False)
    return [actor]


# ── Public: plotter configuration ─────────────────────────────────────────────

def configure_diagnostic_background(plotter: pv.Plotter) -> None:
    """Dark navy [8, 8, 25] background — high contrast for bright wires."""
    plotter.set_background(_NAVY_BG)


def configure_architectural_background(plotter: pv.Plotter) -> None:
    """Pure white background."""
    plotter.set_background((1.0, 1.0, 1.0))


def configure_isometric_view(plotter: pv.Plotter) -> None:
    """
    Set camera to the same slightly-off-axis isometric direction used in
    ``occ_scene`` — eye from (1.2, 0.8, 1.0), Z-up — then fit the scene.

    Each visible face gets a distinct Lambert shading value so the building
    reads clearly as a 3-D solid without appearing distorted.

    Camera position is computed explicitly from the scene bounding box so the
    result is independent of PyVista's ``reset_camera`` heuristics (which can
    place the camera below z=0 when a large ground plane is present).
    """
    bounds = plotter.bounds  # (xmin, xmax, ymin, ymax, zmin, zmax)
    cx = (bounds[0] + bounds[1]) / 2
    cy = (bounds[2] + bounds[3]) / 2
    cz = (bounds[4] + bounds[5]) / 2
    diag = max(bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4])

    eye_dir = np.array([1.2, 0.8, 1.0])
    eye_dir /= np.linalg.norm(eye_dir)
    cam_pos = (cx + eye_dir[0] * diag * 2.5,
               cy + eye_dir[1] * diag * 2.5,
               cz + eye_dir[2] * diag * 2.5)

    plotter.camera.position = cam_pos
    plotter.camera.focal_point = (cx, cy, cz)
    plotter.camera.up = (0.0, 0.0, 1.0)
    plotter.reset_camera_clipping_range()


# ── Public: high-level render_png entry point ─────────────────────────────────

def render_png(
    mass,
    path: str,
    *,
    style: str = "ARCHITECTURAL",
    width: int = 1920,
    height: int = 1080,
    config=None,
    raw_subtractors: list | None = None,
    show_original: bool = False,
    original_mass=None,
    interactive: bool = False,
) -> None:
    """
    Render a building mass to a PNG file (or open an interactive window).

    Parameters
    ----------
    mass
        ``BuildingMass`` (subtracted or plain).
    path
        Output PNG file path.  Ignored when ``interactive=True``.
    style
        ``"DIAGNOSTIC"`` or ``"ARCHITECTURAL"``.
    width, height
        Output resolution in pixels (offscreen mode).
    config
        ``SubtractionConfig`` — if provided, aligned subtractor boxes are shown
        (DIAGNOSTIC style only).
    raw_subtractors
        Pre-alignment ``Subtractor`` list shown in red (DIAGNOSTIC only).
    show_original
        If True, ``original_mass`` is also added as a ghost silhouette.
    original_mass
        Required when ``show_original=True``.
    interactive
        False (default) — renders offscreen and writes PNG; no window shown.
        True — opens an interactive PyVista window (path is ignored).
    """
    off_screen = not interactive
    plotter = pv.Plotter(off_screen=off_screen, window_size=(width, height))

    if style == "ARCHITECTURAL":
        configure_architectural_background(plotter)
    else:
        configure_diagnostic_background(plotter)

    add_building_mass(plotter, mass, style=style)

    if style == "ARCHITECTURAL":
        add_ground_plane(plotter, mass, style="ARCHITECTURAL")
    else:
        if show_original and original_mass is not None:
            add_original_mass(plotter, original_mass)
        if config is not None:
            add_subtractors(plotter, config, raw=raw_subtractors)
        add_cores(plotter, mass)

    configure_isometric_view(plotter)

    if interactive:
        plotter.show(title="BuildingMassOptimizer – PyVista")
    else:
        plotter.show(screenshot=path, auto_close=True)
        print(f"[pyvista_scene] Saved: {path}")
