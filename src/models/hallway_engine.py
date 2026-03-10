from __future__ import annotations

"""
hallway_engine.py — Apply hallway generation to a FloorData or BuildingMass.

Usage examples
--------------
Single floor::

    from models.hallway import HallwayParams
    from models.hallway_engine import apply_hallway_to_floor

    params = HallwayParams(
        floor_polygon=[(0,0),(20,0),(20,20),(0,20)],
        elevation=floor.elevation,
        hallway_width=1.8,
        span_x=4.0,
        span_y=4.0,
        core_locations=[(4.0, 4.0), (16.0, 16.0)],
    )
    apply_hallway_to_floor(floor, params)   # stores result in floor.hallway

Whole building mass::

    from models.hallway_engine import apply_hallway_to_mass

    apply_hallway_to_mass(mass, params)     # updates every floor in place

Notes
-----
* The floor polygon in *params* is re-used for every floor unless
  ``per_floor_polygons`` is provided to ``apply_hallway_to_mass``.
* Only ``elevation`` differs between floors; all other parameters
  (hallway_width, span, cores, …) are shared.
* ``FloorData.hallway`` is always ``None`` after ``BuildingMass.create()``
  and during Individuum generation; this engine populates it post-hoc.
"""

from dataclasses import replace as _dc_replace
from typing import Sequence

from models.building_mass import BuildingMass
from models.floor_data import FloorData
from models.hallway import HallwayLayout, HallwayParams


def apply_hallway_to_floor(
    floor: FloorData,
    params: HallwayParams,
) -> FloorData:
    """Generate a :class:`HallwayLayout` for *floor* and store it in ``floor.hallway``.

    Parameters
    ----------
    floor:
        The target floor; modified **in place** (``floor.hallway`` is set).
    params:
        Hallway parameters.  ``params.elevation`` should match ``floor.elevation``
        if OCC shapes are needed at the correct height; the caller is responsible
        for setting this correctly.

    Returns
    -------
    FloorData
        The same *floor* object (mutated), returned for chaining convenience.
    """
    layout = HallwayLayout.generate(params)
    floor.hallway = layout
    return floor


def apply_hallway_to_mass(
    mass: BuildingMass,
    params: HallwayParams,
    *,
    per_floor_polygons: Sequence[list[tuple[float, float]]] | None = None,
) -> BuildingMass:
    """Apply hallway generation to every floor of *mass*.

    Parameters
    ----------
    mass:
        Target building mass; each ``FloorData.hallway`` is set **in place**.
    params:
        Base hallway parameters.  ``params.floor_polygon`` is used for all
        floors unless *per_floor_polygons* is supplied.
    per_floor_polygons:
        Optional list of polygons, one per floor (index matches
        ``mass.floors``).  When given, each floor gets its own polygon — useful
        for buildings with subtractions where the plan outline varies per floor.
        If ``None``, ``params.floor_polygon`` is used for every floor.

    Returns
    -------
    BuildingMass
        The same *mass* object (floors mutated in place).
    """
    for i, floor in enumerate(mass.floors):
        polygon = (
            per_floor_polygons[i]
            if per_floor_polygons is not None
            else params.floor_polygon
        )
        floor_params = HallwayParams(
            floor_polygon=polygon,
            elevation=floor.elevation,
            hallway_width=params.hallway_width,
            span_x=params.span_x,
            span_y=params.span_y,
            core_locations=params.core_locations,
            max_travel_distance=params.max_travel_distance,
            snap_tolerance=params.snap_tolerance,
            orthog_angle_threshold=params.orthog_angle_threshold,
            pruning_min_length=params.pruning_min_length,
        )
        apply_hallway_to_floor(floor, floor_params)

    return mass
