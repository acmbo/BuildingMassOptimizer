from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SubtractorType(Enum):
    """Distinguishes vertical (tall) from horizontal (flat) subtractors."""
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"


@dataclass
class Subtractor:
    """
    Rectangular box-shaped void for subtractive form generation.

    Both vertical and horizontal subtractors share this structure.
    The cutting solid is:
        BRepPrimAPI_MakeBox(gp_Pnt(x, y, z_bottom), gp_Pnt(x+width, y+depth, z_top))
    """

    x: float
    """X position of subtractor origin (within building footprint)."""

    y: float
    """Y position of subtractor origin (within building footprint)."""

    width: float
    """Extent in X."""

    depth: float
    """Extent in Y."""

    z_bottom: float
    """Absolute Z of the bottom face of the subtractor box."""

    z_top: float
    """Absolute Z of the top face of the subtractor box."""

    subtractor_type: SubtractorType
    """Type metadata — drives constraint validation and communicates design intent."""

    def __post_init__(self) -> None:
        if self.width <= 0:
            raise ValueError(f"Subtractor width must be positive, got {self.width}")
        if self.depth <= 0:
            raise ValueError(f"Subtractor depth must be positive, got {self.depth}")
        if self.z_top <= self.z_bottom:
            raise ValueError(
                f"z_top ({self.z_top}) must be greater than z_bottom ({self.z_bottom})"
            )


@dataclass
class SubtractionConfig:
    """
    Full configuration for a subtractive form generation pass.

    Contains all subtractors and the constraint parameters that govern
    their validation and clamping before any geometry is created.

    Default threshold values come from Wang et al. (2019).
    """

    vertical_subtractors: list[Subtractor] = field(default_factory=list)
    """Vertical subtractors — tall voids (courtyards, atriums, notches)."""

    horizontal_subtractors: list[Subtractor] = field(default_factory=list)
    """Horizontal subtractors — flat voids (stilts, cascades, partial empty floors)."""

    vertical_snap_threshold: float = 0.30
    """
    Fraction of total_height within which a vertical subtractor face is snapped to
    the top or bottom of the maximal volume. At least one face must qualify — otherwise
    the subtractor is deactivated.
    """

    horizontal_max_height_ratio: float = 0.30
    """
    Max allowed height of a horizontal subtractor as a fraction of total_height.
    Vertical extent must satisfy: floor_height <= (z_top - z_bottom) < ratio * total_height.
    Oversized subtractors are clipped; undersized ones are deactivated.
    """

    min_plan_size: float = 0.0
    """
    Minimum allowed width or depth. Subtractors with either dimension below this
    threshold are deactivated entirely.
    """

    max_plan_size: float = float("inf")
    """
    Maximum allowed width or depth. Subtractors with either dimension above this
    threshold are clipped to this value.
    """

    boundary_constraint_enabled: bool = True
    """
    If True (closed boundary): vertical subtractor faces near the outer building wall
    are kept inside, producing enclosed interior voids (courtyards, atriums).
    If False (open boundary): faces near the outer wall are snapped outward, producing
    open notches or slots running through the wall.
    """

    boundary_snap_fraction: float = 0.10
    """
    Fraction of building width/depth within which a subtractor face is considered
    'close' to the outer boundary for boundary snapping (used when
    boundary_constraint_enabled is False).
    """

    def __post_init__(self) -> None:
        if not (0.0 <= self.vertical_snap_threshold <= 1.0):
            raise ValueError(
                f"vertical_snap_threshold must be in [0, 1], got {self.vertical_snap_threshold}"
            )
        if not (0.0 < self.horizontal_max_height_ratio <= 1.0):
            raise ValueError(
                f"horizontal_max_height_ratio must be in (0, 1], got {self.horizontal_max_height_ratio}"
            )
        if self.min_plan_size < 0:
            raise ValueError(
                f"min_plan_size must be >= 0, got {self.min_plan_size}"
            )
        if self.max_plan_size <= 0:
            raise ValueError(
                f"max_plan_size must be > 0, got {self.max_plan_size}"
            )
