from enum import Enum


class CellMode(Enum):
    """Determines how the grid cell size is resolved."""

    FIXED_SIZE = "fixed_size"
    """User provides an absolute cell length in model units."""

    CELL_COUNT = "cell_count"
    """User provides a target cell count along the longest horizontal axis;
    cell size is derived so cells stay square."""
