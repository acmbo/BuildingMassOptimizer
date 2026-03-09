"""
Building core placement engine.

Public API:
    find_building_cores(mass, column_grid, max_face_distance) -> list[BuildingCore]

The algorithm places building cores so that every face (edge) of the ground-floor
footprint polygon is within max_face_distance (default 35 m) of the nearest core.
Placement starts at the footprint centroid and iteratively adds cores at the farthest
uncovered face until all faces are covered.

Each candidate position is snapped to the nearest column-grid cell center (accepted if
the distance is ≤ half the smaller span dimension).
"""
from __future__ import annotations

import math
from typing import NamedTuple

from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_EDGE
from OCC.Core.BRepAdaptor import BRepAdaptor_Curve
from OCC.Core.TopoDS import Edge as topods_Edge

from models.building_core import BuildingCore
from models.building_mass import BuildingMass
from models.column_grid import ColumnGrid


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class _FaceMidpoint(NamedTuple):
    x: float
    y: float


def _extract_face_midpoints(polygon_wire) -> list[_FaceMidpoint]:
    """
    Return the XY midpoint of every edge in polygon_wire.

    Works on both a single wire and a compound (e.g. after subtraction).
    """
    midpoints: list[_FaceMidpoint] = []
    explorer = TopExp_Explorer(polygon_wire, TopAbs_EDGE)
    while explorer.More():
        edge = topods_Edge(explorer.Current())
        curve = BRepAdaptor_Curve(edge)
        p1 = curve.Value(curve.FirstParameter())
        p2 = curve.Value(curve.LastParameter())
        midpoints.append(_FaceMidpoint(
            x=(p1.X() + p2.X()) / 2,
            y=(p1.Y() + p2.Y()) / 2,
        ))
        explorer.Next()
    return midpoints


def _polygon_centroid(midpoints: list[_FaceMidpoint]) -> tuple[float, float]:
    """Approximate centroid as the average of face midpoints."""
    cx = sum(m.x for m in midpoints) / len(midpoints)
    cy = sum(m.y for m in midpoints) / len(midpoints)
    return cx, cy


def _snap_to_column_grid(px: float, py: float, column_grid: ColumnGrid) -> BuildingCore:
    """
    Snap a candidate XY point to the nearest column-grid cell center.

    The snap is accepted when the distance to the nearest cell center is ≤
    0.5 × min(span_x, span_y).  If no cell is within the threshold, the raw
    candidate position is kept while the nearest cell indices are still recorded.
    """
    snap_threshold = 0.5 * min(column_grid.span_x, column_grid.span_y)

    best_dist = math.inf
    best_ix = 0
    best_iy = 0
    best_cx = px
    best_cy = py

    for i in range(len(column_grid.grid_lines_x) - 1):
        cell_cx = column_grid.grid_lines_x[i] + column_grid.span_x / 2
        for j in range(len(column_grid.grid_lines_y) - 1):
            cell_cy = column_grid.grid_lines_y[j] + column_grid.span_y / 2
            d = math.sqrt((px - cell_cx) ** 2 + (py - cell_cy) ** 2)
            if d < best_dist:
                best_dist = d
                best_ix = i
                best_iy = j
                best_cx = cell_cx
                best_cy = cell_cy

    # Use snapped center only when within threshold; otherwise keep raw position
    # but still record the nearest cell indices.
    if best_dist <= snap_threshold:
        center_x, center_y = best_cx, best_cy
    else:
        center_x, center_y = px, py

    return BuildingCore(
        center_x=center_x,
        center_y=center_y,
        width=column_grid.span_x,
        depth=column_grid.span_y,
        column_ix=best_ix,
        column_iy=best_iy,
    )


def _min_distance_to_cores(face: _FaceMidpoint, cores: list[BuildingCore]) -> float:
    return min(
        math.sqrt((face.x - c.center_x) ** 2 + (face.y - c.center_y) ** 2)
        for c in cores
    )


def _is_covered(
    face: _FaceMidpoint,
    cores: list[BuildingCore],
    max_face_distance: float,
) -> bool:
    return _min_distance_to_cores(face, cores) <= max_face_distance


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_building_cores(
    mass: BuildingMass,
    column_grid: ColumnGrid,
    max_face_distance: float = 35.0,
) -> list[BuildingCore]:
    """
    Place building cores so every face of the ground-floor footprint polygon is
    within max_face_distance of the nearest core.

    Parameters
    ----------
    mass              : BuildingMass — the subtracted building mass (ground floor
                        polygon_wire is used for face-distance checks).
    column_grid       : ColumnGrid — provides span sizes and grid-line positions
                        for snapping core centers to column-grid cell centers.
    max_face_distance : Maximum allowed distance from any footprint face midpoint
                        to its nearest core center (default 35 m, per Chinese
                        firefighting evacuation regulation).

    Returns
    -------
    list[BuildingCore] — ordered list of placed cores (at least one).

    Raises
    ------
    ValueError   if the footprint has no edges.
    RuntimeError if the placement loop fails to converge.
    """
    if not mass.floors:
        raise ValueError("BuildingMass has no floors")

    face_midpoints = _extract_face_midpoints(mass.floors[0].polygon_wire)
    if not face_midpoints:
        raise ValueError("Ground-floor polygon wire has no edges")

    cores: list[BuildingCore] = []

    # Step 1: seed with the footprint centroid
    cx, cy = _polygon_centroid(face_midpoints)
    cores.append(_snap_to_column_grid(cx, cy, column_grid))

    # Step 2: iteratively cover uncovered faces
    max_iterations = len(face_midpoints)
    iterations = 0
    while True:
        uncovered = [
            f for f in face_midpoints
            if not _is_covered(f, cores, max_face_distance)
        ]
        if not uncovered:
            break

        if iterations >= max_iterations:
            raise RuntimeError(
                f"Building core placement did not converge after {max_iterations} iterations. "
                f"{len(uncovered)} face(s) remain uncovered (max_face_distance={max_face_distance} m). "
                "This usually means the footprint is very elongated or max_face_distance is too small "
                "relative to the column-grid span."
            )

        farthest = max(uncovered, key=lambda f: _min_distance_to_cores(f, cores))
        cores.append(_snap_to_column_grid(farthest.x, farthest.y, column_grid))
        iterations += 1

    return cores
