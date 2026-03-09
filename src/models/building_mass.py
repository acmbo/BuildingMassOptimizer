from __future__ import annotations

from dataclasses import dataclass, field

from floorgeneration import create_wire, create_polygon, translate_shape, extrude_face
from models.floor_data import FloorData


@dataclass
class BuildingMass:
    """
    Top-level container for a building mass made of stacked floor extrusions.

    Create via the classmethod:
        mass = BuildingMass.create(polygon_points, floor_height, num_floors)
    """

    polygon_points: list[tuple[float, float, float]]
    """Original input polygon in the XY plane (z values are ignored during generation)."""

    floor_height: float
    """Uniform floor height used during generation."""

    num_floors: int
    """Total number of floors."""

    floors: list[FloorData]
    """Ordered list of floors, index 0 = ground floor."""

    cores: list = field(default_factory=list)
    """Building cores for this mass.  Populated by find_building_cores()."""

    total_height: float = field(init=False)
    """Derived total building height (floor_height × num_floors)."""

    def __post_init__(self) -> None:
        self.total_height = self.floor_height * self.num_floors

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        polygon_points: list[tuple[float, float, float]],
        floor_height: float,
        num_floors: int,
    ) -> BuildingMass:
        """
        Generate a BuildingMass from a flat polygon, a floor height, and a
        number of floors.

        For each floor i (0-indexed):
          - The polygon wire is placed at elevation = floor_height * i.
          - The face is extruded upward by floor_height to form a solid.
        """
        base_face = create_polygon(polygon_points)
        floors: list[FloorData] = []

        for i in range(num_floors):
            elevation = floor_height * i

            if elevation == 0:
                floor_face = base_face
            else:
                floor_face = translate_shape(base_face, elevation)

            solid = extrude_face(floor_face, floor_height)
            wire = create_wire(polygon_points, z_offset=elevation)

            floors.append(FloorData(
                index=i,
                elevation=elevation,
                floor_height=floor_height,
                solid=solid,
                polygon_wire=wire,
            ))

        return cls(
            polygon_points=polygon_points,
            floor_height=floor_height,
            num_floors=num_floors,
            floors=floors,
        )

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"BuildingMass("
            f"num_floors={self.num_floors}, "
            f"floor_height={self.floor_height}, "
            f"total_height={self.total_height})"
        )
