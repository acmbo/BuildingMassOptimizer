"""
Architectural visualization utilities for BuildingMassOptimizer.

Public API — 2D floor plans (matplotlib)
-----------------------------------------
draw_floor_plan(ax, floor, *, column_grid, original_footprint, ...)
    Render one FloorData as an architectural section-cut floor plan.

draw_floor_plan_grid(floors, *, column_grid, original_footprint, ...)
    Compose multiple floor plans into a matplotlib figure.

DEFAULT_PALETTE
    Default color token dictionary (see visualization.palette).

Public API — 3D OCC scene (pythonocc)
--------------------------------------
add_building_mass, add_original_mass, add_subtractors, add_cores,
add_ground_plane, add_directional_light,
configure_diagnostic_background, configure_architectural_background,
configure_isometric_view, configure_ray_tracing,
export_png, render_png
    Modular OCC display helpers (see visualization.occ_scene).
"""

from visualization.floor_plan import draw_floor_plan, draw_floor_plan_grid
from visualization.palette import DEFAULT_PALETTE, merge_palette
from visualization.occ_scene import (
    add_building_mass,
    add_original_mass,
    add_subtractors,
    add_cores,
    add_ground_plane,
    add_directional_light,
    configure_diagnostic_background,
    configure_architectural_background,
    configure_isometric_view,
    configure_ray_tracing,
    export_png,
    render_png,
)

__all__ = [
    # 2D floor plans
    "draw_floor_plan",
    "draw_floor_plan_grid",
    "DEFAULT_PALETTE",
    "merge_palette",
    # 3D OCC scene
    "add_building_mass",
    "add_original_mass",
    "add_subtractors",
    "add_cores",
    "add_ground_plane",
    "add_directional_light",
    "configure_diagnostic_background",
    "configure_architectural_background",
    "configure_isometric_view",
    "configure_ray_tracing",
    "export_png",
    "render_png",
]
