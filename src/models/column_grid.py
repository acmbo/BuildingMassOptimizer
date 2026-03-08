from __future__ import annotations

import math
from dataclasses import dataclass, field

from models.building_mass import BuildingMass
from models.span_mode import SpanMode


@dataclass
class ColumnGrid:
    """
    2-D structural column grid fitted to the XY bounding box of a BuildingMass polygon.

    The grid is building-wide (no Z dimension) — the same X/Y lines apply to every
    floor. Its purpose is to provide alignment positions (quarter-span snapping) for
    subtractors, ensuring all subtracted faces land on structurally coherent positions.

    Create via the classmethod:
        grid = ColumnGrid.create(mass, SpanMode.FIXED_SPAN, span_x=4.0, span_y=4.0)
        grid = ColumnGrid.create(mass, SpanMode.SPAN_COUNT, nx_spans=3, ny_spans=2)
    """

    span_mode: SpanMode
    """Strategy used to resolve span sizes."""

    span_x: float
    """Column spacing along X (model units)."""

    span_y: float
    """Column spacing along Y (model units)."""

    nx_spans: int
    """Number of column spans along X (columns in X = nx_spans + 1)."""

    ny_spans: int
    """Number of column spans along Y (columns in Y = ny_spans + 1)."""

    origin_x: float
    """X coordinate of the first column line — derived from polygon bbox min X."""

    origin_y: float
    """Y coordinate of the first column line — derived from polygon bbox min Y."""

    grid_lines_x: list[float]
    """Absolute X positions of all column lines (nx_spans + 1 values)."""

    grid_lines_y: list[float]
    """Absolute Y positions of all column lines (ny_spans + 1 values)."""

    total_width: float = field(init=False)
    """Total X extent covered by the grid (nx_spans × span_x). Derived."""

    total_depth: float = field(init=False)
    """Total Y extent covered by the grid (ny_spans × span_y). Derived."""

    snap_positions_x: list[float] = field(init=False)
    """All quarter-span snap positions along X (nx_spans × 4 + 1 values). Derived."""

    snap_positions_y: list[float] = field(init=False)
    """All quarter-span snap positions along Y (ny_spans × 4 + 1 values). Derived."""

    def __post_init__(self) -> None:
        self.total_width = self.nx_spans * self.span_x
        self.total_depth = self.ny_spans * self.span_y
        self.snap_positions_x = [
            self.origin_x + i * self.span_x / 4
            for i in range(self.nx_spans * 4 + 1)
        ]
        self.snap_positions_y = [
            self.origin_y + j * self.span_y / 4
            for j in range(self.ny_spans * 4 + 1)
        ]

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        building_mass: BuildingMass,
        span_mode: SpanMode,
        span_x: float | None = None,
        span_y: float | None = None,
        nx_spans: int | None = None,
        ny_spans: int | None = None,
    ) -> ColumnGrid:
        """
        Generate a ColumnGrid fitted to the XY bounding box of a BuildingMass polygon.

        Parameters
        ----------
        building_mass : BuildingMass
        span_mode     : SpanMode.FIXED_SPAN or SpanMode.SPAN_COUNT
        span_x        : required for FIXED_SPAN — column spacing along X in model units
        span_y        : required for FIXED_SPAN — column spacing along Y in model units
        nx_spans      : required for SPAN_COUNT — number of column spans along X
        ny_spans      : required for SPAN_COUNT — number of column spans along Y
        """
        if not building_mass.polygon_points:
            raise ValueError("building_mass must have polygon_points")

        pts = building_mass.polygon_points
        poly_xmin = min(p[0] for p in pts)
        poly_xmax = max(p[0] for p in pts)
        poly_ymin = min(p[1] for p in pts)
        poly_ymax = max(p[1] for p in pts)

        bbox_width = poly_xmax - poly_xmin
        bbox_depth = poly_ymax - poly_ymin

        if span_mode == SpanMode.FIXED_SPAN:
            if span_x is None or span_x <= 0:
                raise ValueError("span_x must be positive")
            if span_y is None or span_y <= 0:
                raise ValueError("span_y must be positive")
            nx_spans = math.ceil(bbox_width / span_x)
            ny_spans = math.ceil(bbox_depth / span_y)

        elif span_mode == SpanMode.SPAN_COUNT:
            if nx_spans is None or nx_spans < 1:
                raise ValueError("nx_spans must be at least 1")
            if ny_spans is None or ny_spans < 1:
                raise ValueError("ny_spans must be at least 1")
            span_x = bbox_width / nx_spans
            span_y = bbox_depth / ny_spans

        else:
            raise ValueError(f"Unknown span_mode: {span_mode!r}")

        origin_x = poly_xmin
        origin_y = poly_ymin

        grid_lines_x = [origin_x + i * span_x for i in range(nx_spans + 1)]
        grid_lines_y = [origin_y + j * span_y for j in range(ny_spans + 1)]

        return cls(
            span_mode=span_mode,
            span_x=span_x,
            span_y=span_y,
            nx_spans=nx_spans,
            ny_spans=ny_spans,
            origin_x=origin_x,
            origin_y=origin_y,
            grid_lines_x=grid_lines_x,
            grid_lines_y=grid_lines_y,
        )

    # ------------------------------------------------------------------
    # Snap operations
    # ------------------------------------------------------------------

    def snap_to_grid(self, v: float, axis: str) -> float:
        """
        Return the nearest quarter-span position on the given axis.

        Parameters
        ----------
        v    : coordinate value to snap
        axis : 'x' or 'y'
        """
        if axis == "x":
            positions = self.snap_positions_x
        elif axis == "y":
            positions = self.snap_positions_y
        else:
            raise ValueError(f"axis must be 'x' or 'y', got {axis!r}")
        return min(positions, key=lambda p: abs(p - v))

    def align_subtractor(self, sub):
        """
        Snap all four plan faces of a Subtractor to the nearest quarter-span positions.

        The Z range (z_bottom, z_top) is preserved unchanged — Z is irrelevant to
        plan alignment and the same grid applies to every floor.

        Returns a new Subtractor with snapped x, y, width, depth, or None if the
        snapped width or depth is <= 0 (subtractor deactivated).
        """
        from models.subtractor import Subtractor

        snapped_x = self.snap_to_grid(sub.x, "x")
        snapped_x_far = self.snap_to_grid(sub.x + sub.width, "x")
        snapped_y = self.snap_to_grid(sub.y, "y")
        snapped_y_far = self.snap_to_grid(sub.y + sub.depth, "y")

        new_width = snapped_x_far - snapped_x
        new_depth = snapped_y_far - snapped_y

        if new_width <= 0 or new_depth <= 0:
            return None

        return Subtractor(
            x=snapped_x,
            y=snapped_y,
            width=new_width,
            depth=new_depth,
            z_bottom=sub.z_bottom,
            z_top=sub.z_top,
            subtractor_type=sub.subtractor_type,
        )

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"ColumnGrid("
            f"nx_spans={self.nx_spans}, ny_spans={self.ny_spans}, "
            f"span_x={self.span_x:.3f}, span_y={self.span_y:.3f}, "
            f"origin=({self.origin_x:.3f}, {self.origin_y:.3f}))"
        )
