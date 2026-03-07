from dataclasses import dataclass, field


@dataclass
class GridCell:
    """A single cell in the building grid."""

    ix: int
    """Column index along the X axis (0-based)."""

    iy: int
    """Row index along the Y axis (0-based)."""

    iz: int
    """Floor index along the Z axis (0-based, matches FloorData.index)."""

    min_pt: tuple[float, float, float]
    """Minimum corner of the cell (xmin, ymin, zmin)."""

    max_pt: tuple[float, float, float]
    """Maximum corner of the cell (xmax, ymax, zmax)."""

    center: tuple[float, float, float] = field(init=False)
    """Cell centre point, derived from min_pt and max_pt."""

    def __post_init__(self) -> None:
        self.center = (
            (self.min_pt[0] + self.max_pt[0]) / 2,
            (self.min_pt[1] + self.max_pt[1]) / 2,
            (self.min_pt[2] + self.max_pt[2]) / 2,
        )
