"""
Modular OCC 3D scene building helpers for BuildingMassOptimizer.

Public API
----------
add_building_mass(context, mass, *, style, show_floor_wires) -> list
    Add floor solids (and polygon wires) to the AIS context.

add_original_mass(context, mass) -> list
    Add the uncut original mass as a faint ghost silhouette.

add_subtractors(context, config, *, raw, aligned_only) -> list
    Add subtractor boxes: raw list in red, config-aligned in orange.

add_cores(context, mass) -> list
    Add building core boxes spanning full height.

add_ground_plane(context, mass, *, padding_factor, style) -> list
    Add a flat ground slab at z=0, extending beyond the building footprint.

configure_diagnostic_background(display) -> None
    Set dark navy gradient background.

configure_architectural_background(display) -> None
    Set light grey-to-white gradient background.

configure_isometric_view(display) -> None
    Set camera to true isometric (eye from +X+Y+Z) and call FitAll.

configure_ray_tracing(display) -> None
    Enable Graphic3d_RM_RAYTRACING with shadows and ambient occlusion.

export_png(display, path, delay_ms) -> None
    Schedule a V3d_View.Dump via Tk after() callback (interactive mode only).

render_png(mass, path, *, style, headless, width, height, config, show_original) -> None
    High-level convenience: full render to PNG in interactive or headless mode.

Visual styles
-------------
DIAGNOSTIC
    Dark navy background. Semi-transparent white building, cyan floor wires,
    red wireframe for raw subtractors, orange wireframe for aligned subtractors,
    semi-transparent blue cores.

ARCHITECTURAL
    Light grey-white background. Fully opaque white plaster building, white
    ground plane, directional light, ray-traced shadows and ambient occlusion.
    No floor wires, no subtractor boxes, no original ghost.
"""

from __future__ import annotations

from OCC.Core.AIS import AIS_Shape
from OCC.Core.Aspect import Aspect_TOL_DOT, Aspect_TOL_SOLID
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.gp import gp_Pnt, gp_Dir
from OCC.Core.Prs3d import Prs3d_LineAspect, Prs3d_ShadingAspect
from OCC.Core.Quantity import (
    Quantity_Color,
    Quantity_TOC_RGB,
    Quantity_NOC_WHITE,
    Quantity_NOC_RED,
    Quantity_NOC_GRAY60,
)


# ── Colour constants ───────────────────────────────────────────────────────────

_WHITE  = Quantity_Color(Quantity_NOC_WHITE)
_GRAY   = Quantity_Color(Quantity_NOC_GRAY60)
_RED    = Quantity_Color(Quantity_NOC_RED)
_CYAN   = Quantity_Color(0.2,  0.9,  0.9,  Quantity_TOC_RGB)
_ORANGE = Quantity_Color(1.0,  0.55, 0.1,  Quantity_TOC_RGB)
_BLUE   = Quantity_Color(0.15, 0.45, 1.0,  Quantity_TOC_RGB)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _make_ais_solid(
    shape,
    color: Quantity_Color,
    transparency: float,
    line_type=Aspect_TOL_DOT,
    line_width: float = 1.2,
) -> AIS_Shape:
    """AIS_Shape with shading + matching edge styling."""
    ais = AIS_Shape(shape)
    drawer = ais.Attributes()

    shading = Prs3d_ShadingAspect()
    shading.SetColor(color)
    shading.SetTransparency(transparency)
    drawer.SetShadingAspect(shading)

    edge = Prs3d_LineAspect(color, line_type, line_width)
    drawer.SetWireAspect(edge)
    drawer.SetFaceBoundaryAspect(edge)
    drawer.SetFaceBoundaryDraw(True)
    return ais


def _make_ais_wireframe(
    shape,
    color: Quantity_Color,
    line_width: float = 1.5,
) -> AIS_Shape:
    """AIS_Shape styled as a wireframe (faces fully transparent, solid edges)."""
    ais = AIS_Shape(shape)
    drawer = ais.Attributes()

    shading = Prs3d_ShadingAspect()
    shading.SetColor(color)
    shading.SetTransparency(1.0)
    drawer.SetShadingAspect(shading)

    edge = Prs3d_LineAspect(color, Aspect_TOL_SOLID, line_width)
    drawer.SetWireAspect(edge)
    drawer.SetFaceBoundaryAspect(edge)
    drawer.SetFaceBoundaryDraw(True)
    return ais


def _make_ais_plaster(shape, color: Quantity_Color) -> AIS_Shape:
    """AIS_Shape with opaque white shading (architectural style). No edge lines."""
    ais = AIS_Shape(shape)
    drawer = ais.Attributes()

    shading = Prs3d_ShadingAspect()
    shading.SetColor(color)
    shading.SetTransparency(0.0)
    drawer.SetShadingAspect(shading)
    drawer.SetFaceBoundaryDraw(False)
    return ais


def _display_solid(context, ais: AIS_Shape) -> None:
    context.Display(ais, False)
    context.SetDisplayMode(ais, 1, False)


def _subtractor_box(sub):
    """BRep box for a Subtractor."""
    return BRepPrimAPI_MakeBox(
        gp_Pnt(sub.x,             sub.y,             sub.z_bottom),
        gp_Pnt(sub.x + sub.width, sub.y + sub.depth, sub.z_top),
    ).Shape()


# ── Public: add elements to AIS context ───────────────────────────────────────

def add_building_mass(
    context,
    mass,
    *,
    style: str = "DIAGNOSTIC",
    show_floor_wires: bool = True,
) -> list:
    """
    Add all floor solids (and wires) to the AIS context.

    Parameters
    ----------
    context
        AIS_InteractiveContext — typically ``display.Context``.
    mass
        BuildingMass with ``.floors``.
    style
        ``"DIAGNOSTIC"`` — semi-transparent white + cyan wires (default).
        ``"ARCHITECTURAL"`` — opaque white plaster, no wires.
    show_floor_wires
        When True and style is DIAGNOSTIC, cyan polygon-wire overlays are added.

    Returns
    -------
    list of AIS_Shape
    """
    result = []
    if style == "ARCHITECTURAL":
        arch_white = Quantity_Color(0.92, 0.92, 0.92, Quantity_TOC_RGB)
        for floor in mass.floors:
            ais = _make_ais_plaster(floor.solid, arch_white)
            _display_solid(context, ais)
            result.append(ais)
    else:
        for floor in mass.floors:
            ais = _make_ais_solid(floor.solid, _WHITE, 0.82)
            _display_solid(context, ais)
            result.append(ais)
            if show_floor_wires:
                ais_wire = AIS_Shape(floor.polygon_wire)
                wire_drawer = ais_wire.Attributes()
                wire_line = Prs3d_LineAspect(_CYAN, Aspect_TOL_SOLID, 2.0)
                wire_drawer.SetWireAspect(wire_line)
                context.Display(ais_wire, False)
                result.append(ais_wire)
    return result


def add_original_mass(context, mass) -> list:
    """
    Add the uncut original mass as a faint ghost silhouette.

    Rendered with 0.97 transparency, dot-line edges, GRAY60 colour.
    """
    result = []
    for floor in mass.floors:
        ais = _make_ais_solid(floor.solid, _GRAY, 0.97, Aspect_TOL_DOT, 0.5)
        _display_solid(context, ais)
        result.append(ais)
    return result


def add_subtractors(
    context,
    config,
    *,
    raw: list | None = None,
    aligned_only: bool = False,
) -> list:
    """
    Add subtractor boxes to the AIS context.

    Parameters
    ----------
    context
        AIS_InteractiveContext.
    config
        SubtractionConfig — aligned subtractors drawn in **orange** wireframe.
        Pass ``None`` to skip aligned boxes.
    raw
        List of pre-alignment Subtractor objects drawn in **red** wireframe.
        Ignored when ``aligned_only=True``.
    aligned_only
        When True, skip the raw (red) boxes even if ``raw`` is provided.
    """
    result = []
    if raw is not None and not aligned_only:
        for sub in raw:
            ais = _make_ais_wireframe(_subtractor_box(sub), _RED, 1.0)
            _display_solid(context, ais)
            result.append(ais)
    if config is not None:
        aligned = config.vertical_subtractors + config.horizontal_subtractors
        for sub in aligned:
            ais = _make_ais_wireframe(_subtractor_box(sub), _ORANGE, 2.0)
            _display_solid(context, ais)
            result.append(ais)
    return result


def add_cores(context, mass) -> list:
    """
    Add building core boxes to the AIS context.

    Each core is extruded from z=0 to total_height as a semi-transparent
    blue solid.
    """
    result = []
    cores = getattr(mass, "cores", None) or []
    total_height = mass.total_height
    for core in cores:
        box = BRepPrimAPI_MakeBox(
            gp_Pnt(core.x_min, core.y_min, 0.0),
            gp_Pnt(core.x_max, core.y_max, total_height),
        ).Shape()
        ais = _make_ais_solid(box, _BLUE, 0.55, Aspect_TOL_SOLID, 2.0)
        _display_solid(context, ais)
        result.append(ais)
    return result


def add_ground_plane(
    context,
    mass,
    *,
    padding_factor: float = 0.4,
    style: str = "ARCHITECTURAL",
) -> list:
    """
    Add a thin flat ground slab at z=0 extending beyond the building footprint.

    The slab spans from z=−0.05 to z=0.0 so the building sits cleanly on it.

    Parameters
    ----------
    padding_factor
        Fraction of max(bbox_width, bbox_depth) added as margin on all sides.
    style
        ``"ARCHITECTURAL"`` → opaque white plaster.
        ``"DIAGNOSTIC"`` → light grey, slightly transparent.
    """
    xs = [p[0] for p in mass.polygon_points]
    ys = [p[1] for p in mass.polygon_points]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    pad = max(xmax - xmin, ymax - ymin) * padding_factor
    ground_shape = BRepPrimAPI_MakeBox(
        gp_Pnt(xmin - pad, ymin - pad, -0.05),
        gp_Pnt(xmax + pad, ymax + pad,  0.00),
    ).Shape()
    if style == "ARCHITECTURAL":
        arch_white = Quantity_Color(1.0, 1.0, 1.0, Quantity_TOC_RGB)
        ais = _make_ais_plaster(ground_shape, arch_white)
    else:
        light_gray = Quantity_Color(0.85, 0.85, 0.85, Quantity_TOC_RGB)
        ais = _make_ais_solid(ground_shape, light_gray, 0.3)
    _display_solid(context, ais)
    return [ais]


# ── Public: display configuration ─────────────────────────────────────────────

def configure_diagnostic_background(display) -> None:
    """Dark navy gradient [8, 8, 25] — high contrast for bright wires."""
    dark = [8, 8, 25]
    display.set_bg_gradient_color(dark, dark)


def configure_architectural_background(display) -> None:
    """Pure white background + hide axis triedron for clean architectural look."""
    white = [255, 255, 255]
    display.set_bg_gradient_color(white, white)
    try:
        display.hide_triedron()
    except Exception:
        pass


def configure_isometric_view(display) -> None:
    """
    Set camera to a true isometric direction (eye from +X, +Y, +Z) and FitAll.

    The view projection is set to (1, 1, 1) from origin, Z-up.  Call this
    *after* all geometry has been added so FitAll covers all shapes.
    """
    # Slightly off-axis isometric: (1.3, 0.7, 1.0) instead of (1,1,1).
    # In exact isometric all three visible face normals are at the same angle
    # to the headlight, producing uniform grey. The offset gives each face a
    # distinct Lambert factor (left≈0.70, top≈0.53, right≈0.37) so the
    # building reads clearly as a 3D solid without changing the visual impression.
    display.View.SetProj(1.2, 0.8, 1.0)
    display.View.SetUp(0.0, 0.0, 1.0)
    display.FitAll()


def configure_ray_tracing(display) -> None:
    """
    Enable OCC ray-tracing with shadows and ambient occlusion.

    Requires OpenGL 4.  Falls back gracefully (prints a warning) if the
    GPU or driver does not support ray-tracing.

    Must be called *before* ``start_display()``.
    """
    try:
        from OCC.Core.Graphic3d import Graphic3d_RM_RAYTRACING
        rp = display.View.ChangeRenderingParams()
        rp.Method                   = Graphic3d_RM_RAYTRACING
        rp.IsShadowEnabled          = True
        rp.IsAmbientOcclusionEnabled = True
        rp.IsReflectionEnabled      = False
        rp.RaytracingDepth          = 3
    except Exception as exc:
        print(f"[occ_scene] Ray-tracing unavailable ({exc}). Using Phong shading.")


def add_directional_light(display) -> None:
    """
    Add a directional light from the upper-left-front (NW sun, 45° elevation).

    Produces cast shadows on the ground plane that reveal voids and overhangs.
    Call this in ARCHITECTURAL mode before ``start_display()``.
    """
    try:
        from OCC.Core.Graphic3d import (
            Graphic3d_CLight,
            Graphic3d_TOLS_DIRECTIONAL,
            Graphic3d_TOLS_AMBIENT,
        )

        # Remove default lights (headlight + ambient) so we own the balance.
        display.Viewer.SetLightOff()

        # Dim ambient: prevents pitch-black on shadowed faces.
        ambient = Graphic3d_CLight(Graphic3d_TOLS_AMBIENT)
        ambient.SetColor(Quantity_Color(0.15, 0.15, 0.15, Quantity_TOC_RGB))
        display.Viewer.AddLight(ambient)

        # Primary sun: upper-right of the isometric view (eye at 1,1,1, Z-up).
        # Visible-face Lambert factors (normalised sun (0.5,-1.0,-2.0)):
        #   top  (0,0,1): 0.87  → ambient + 0.87 ≈ near-white
        #   right(0,1,0): 0.44  → ambient + 0.44 ≈ medium grey
        #   left (1,0,0): 0.00  → ambient only  ≈ dark grey
        sun = Graphic3d_CLight(Graphic3d_TOLS_DIRECTIONAL)
        sun.SetDirection(gp_Dir(0.5, -1.0, -2.0))
        sun.SetColor(Quantity_Color(1.0, 1.0, 1.0, Quantity_TOC_RGB))
        sun.SetIntensity(1.0)
        display.Viewer.AddLight(sun)

        display.Viewer.SetLightOn()
        try:
            display.View.SetLightOn()
        except Exception:
            pass
    except Exception as exc:
        print(f"[occ_scene] Directional light setup failed ({exc}). Using default lighting.")


# ── Public: PNG export ─────────────────────────────────────────────────────────

def export_png(display, path: str, delay_ms: int = 300) -> None:
    """
    Schedule a ``V3d_View.Dump`` of the current framebuffer to *path*.

    The Tk ``after`` callback fires *delay_ms* milliseconds after the event
    loop starts, allowing at least one render cycle to complete before the
    framebuffer is captured.  The viewer stays open after the export.

    Only valid when using the interactive (SimpleGui / Tkinter) display.
    Falls back to an immediate Dump if the Tk canvas is not accessible.

    Parameters
    ----------
    display
        Display object returned by ``init_display()``.
    path
        Output PNG file path.
    delay_ms
        Delay in milliseconds before capturing.  Default 300 ms.
    """
    def _dump():
        display.View.Dump(path)
        print(f"[occ_scene] Saved: {path}")

    try:
        tk_canvas = display._window.canvas._canvas
        tk_canvas.after(delay_ms, _dump)
    except AttributeError:
        # Fallback: Tk canvas path not accessible; dump immediately.
        _dump()


# ── Public: high-level render_png entry point ─────────────────────────────────

def render_png(
    mass,
    path: str,
    *,
    style: str = "ARCHITECTURAL",
    headless: bool = False,
    width: int = 1920,
    height: int = 1080,
    config=None,
    show_original: bool = False,
    raw_subtractors: list | None = None,
) -> None:
    """
    Render a building mass to a PNG file.

    Parameters
    ----------
    mass
        BuildingMass (subtracted).
    path
        Output PNG file path.
    style
        ``"DIAGNOSTIC"`` or ``"ARCHITECTURAL"``.
    headless
        False (default) — opens an OCC SimpleGui window, sets the isometric
        camera, exports the PNG via a Tk callback, and keeps the viewer open.
        True — uses an ``Aspect_NeutralWindow`` offscreen OpenGL context.
        No window is displayed.  Suitable for batch / CI use.
    width, height
        Output resolution (headless mode only; interactive uses window size).
    config
        SubtractionConfig — if provided, subtractor boxes are shown (DIAGNOSTIC).
    show_original
        If True, also pass the original mass to ``add_original_mass``.
        ``mass`` must already be the subtracted mass; you must supply the
        original mass via the ``original_mass`` keyword (not yet wired here —
        use the lower-level ``add_original_mass`` call for this).
    raw_subtractors
        Pre-alignment Subtractor list shown in red (DIAGNOSTIC, headless=False).
    """
    if headless:
        _render_headless(
            mass, path,
            style=style, width=width, height=height,
            config=config, raw_subtractors=raw_subtractors,
        )
    else:
        _render_interactive(
            mass, path,
            style=style, config=config,
            raw_subtractors=raw_subtractors,
        )


def _render_interactive(mass, path, *, style, config, raw_subtractors) -> None:
    """Open an interactive OCC viewer and export a PNG via Tk callback."""
    from OCC.Display.SimpleGui import init_display

    display, start_display, _add_menu, _add_fn = init_display()

    if style == "ARCHITECTURAL":
        configure_architectural_background(display)
    else:
        configure_diagnostic_background(display)

    context = display.Context

    add_building_mass(context, mass, style=style)

    if style == "ARCHITECTURAL":
        add_ground_plane(context, mass, style="ARCHITECTURAL")
        add_directional_light(display)
        configure_ray_tracing(display)
    else:
        if config is not None:
            add_subtractors(context, config, raw=raw_subtractors)
        add_cores(context, mass)

    configure_isometric_view(display)
    export_png(display, path)
    start_display()


def _render_headless(mass, path, *, style, width, height, config, raw_subtractors) -> None:
    """
    Render to PNG using an Aspect_NeutralWindow offscreen OpenGL context.

    No window is opened.  Requires an OpenGL driver that supports offscreen
    rendering (Mesa or hardware).

    Falls back with a helpful error message if the offscreen context cannot
    be created — in that case, use Xvfb:

        Xvfb :99 -screen 0 1920x1080x24 &
        DISPLAY=:99 python your_script.py
    """
    try:
        from OCC.Core.Aspect import Aspect_NeutralWindow
        from OCC.Core.OpenGl import OpenGl_GraphicDriver
        from OCC.Core.V3d import V3d_Viewer
        from OCC.Core.AIS import AIS_InteractiveContext

        graphic_driver = OpenGl_GraphicDriver()
        viewer = V3d_Viewer(graphic_driver)
        view = viewer.CreateView()

        offscreen_window = Aspect_NeutralWindow()
        offscreen_window.SetSize(width, height)
        view.SetWindow(offscreen_window)
        if not offscreen_window.IsMapped():
            offscreen_window.Map()

        context = AIS_InteractiveContext(viewer)

        # Wire style calls directly against the AIS context
        add_building_mass(context, mass, style=style)
        if style == "ARCHITECTURAL":
            add_ground_plane(context, mass, style="ARCHITECTURAL")
        else:
            if config is not None:
                add_subtractors(context, config, raw=raw_subtractors)
            add_cores(context, mass)

        view.SetProj(1.0, 1.0, 1.0)
        view.SetUp(0.0, 0.0, 1.0)
        view.FitAll()
        view.Redraw()
        view.Dump(path)
        print(f"[occ_scene] Saved: {path}")

    except Exception as exc:
        raise RuntimeError(
            f"Headless rendering failed: {exc}\n\n"
            "Fallback — use Xvfb (zero code change):\n"
            "    Xvfb :99 -screen 0 1920x1080x24 &\n"
            "    DISPLAY=:99 python your_script.py\n"
        ) from exc
