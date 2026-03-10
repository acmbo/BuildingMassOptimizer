from __future__ import annotations

from dataclasses import dataclass, field

from OCC.Core.TopoDS import TopoDS_Shape


@dataclass
class FloorData:
    """All geometry and metadata for a single floor."""

    index: int
    """0-based floor number (0 = ground floor)."""

    elevation: float
    """Z position of the bottom face in model units."""

    floor_height: float
    """Height of this floor. Stored per floor to allow variable heights later."""

    solid: TopoDS_Shape
    """Extruded solid volume — use for Booleans, area/volume analysis, and export."""

    polygon_wire: TopoDS_Shape
    """Closed wire at the bottom face elevation — use for floor-plan rendering and offsets.

    After subtraction this becomes a compound of wires: the outer boundary plus one inner
    wire per void (courtyard, atrium, notch).  The wires are not tagged — use
    BRepClass3d_SolidClassifier on ``solid`` to distinguish inside from outside material,
    rather than trying to parse outer-vs-inner wire orientation from this compound.
    """

    cores: list = field(default_factory=list)
    """Building cores active on this floor.  Populated by find_building_cores()."""

    hallway: object = field(default=None)
    """HallwayLayout for this floor, or None.  Set by apply_hallway_to_floor() /
    apply_hallway_to_mass() in hallway_engine.py.  Always None during Individuum
    generation — the field is never touched by the EA pipeline."""
