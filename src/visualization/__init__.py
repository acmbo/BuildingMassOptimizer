"""
Architectural visualization utilities for BuildingMassOptimizer.

Public API
----------
draw_floor_plan(ax, floor, *, column_grid, original_footprint, ...)
    Render one FloorData as an architectural section-cut floor plan.

draw_floor_plan_grid(floors, *, column_grid, original_footprint, ...)
    Compose multiple floor plans into a matplotlib figure.

DEFAULT_PALETTE
    Default color token dictionary (see visualization.palette).
"""

from visualization.floor_plan import draw_floor_plan, draw_floor_plan_grid
from visualization.palette import DEFAULT_PALETTE, merge_palette

__all__ = [
    "draw_floor_plan",
    "draw_floor_plan_grid",
    "DEFAULT_PALETTE",
    "merge_palette",
]
