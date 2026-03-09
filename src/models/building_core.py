from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BuildingCore:
    """
    A single building core: a vertical service zone (circulation, evacuation,
    structural support) placed at a column-grid cell center.

    The core spans the full building height; Z bounds are read from BuildingMass.
    Plan position is snapped to the nearest column-grid cell center by
    find_building_cores().
    """

    center_x: float
    """X coordinate of the core center in model units."""

    center_y: float
    """Y coordinate of the core center in model units."""

    width: float
    """Core footprint width in X (defaults to column_grid.span_x)."""

    depth: float
    """Core footprint depth in Y (defaults to column_grid.span_y)."""

    column_ix: int
    """Column-grid cell index along X (0-based)."""

    column_iy: int
    """Column-grid cell index along Y (0-based)."""

    def __post_init__(self) -> None:
        if self.width <= 0:
            raise ValueError(f"BuildingCore.width must be positive, got {self.width}")
        if self.depth <= 0:
            raise ValueError(f"BuildingCore.depth must be positive, got {self.depth}")
        if self.column_ix < 0:
            raise ValueError(f"BuildingCore.column_ix must be >= 0, got {self.column_ix}")
        if self.column_iy < 0:
            raise ValueError(f"BuildingCore.column_iy must be >= 0, got {self.column_iy}")

    # ------------------------------------------------------------------
    # Derived edges
    # ------------------------------------------------------------------

    @property
    def x_min(self) -> float:
        """Left edge of the core footprint."""
        return self.center_x - self.width / 2

    @property
    def x_max(self) -> float:
        """Right edge of the core footprint."""
        return self.center_x + self.width / 2

    @property
    def y_min(self) -> float:
        """Front edge of the core footprint."""
        return self.center_y - self.depth / 2

    @property
    def y_max(self) -> float:
        """Back edge of the core footprint."""
        return self.center_y + self.depth / 2

    def __repr__(self) -> str:
        return (
            f"BuildingCore("
            f"center=({self.center_x:.2f}, {self.center_y:.2f}), "
            f"size=({self.width:.2f}×{self.depth:.2f}), "
            f"cell=({self.column_ix}, {self.column_iy}))"
        )
