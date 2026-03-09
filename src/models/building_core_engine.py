"""
Building core placement engine.

Public API:
    find_building_cores(mass, column_grid, max_face_distance) -> list[BuildingCore]

The algorithm places building cores so that every face (edge) of the ground-floor
footprint polygon is within max_face_distance (default 35 m) of the nearest core.
Placement starts at the footprint centroid and iteratively adds cores at the farthest
uncovered face until all faces are covered.

Each candidate position is snapped to the nearest column-grid cell center whose center
lies inside the subtracted solid on **every** floor (accepted if the distance is ≤ half
the smaller span dimension).  Checking all floors prevents placing a core inside a void
that only appears on upper floors (e.g. a partial-height horizontal subtractor).  If no
valid cell is within the snap threshold the raw candidate position is used, provided it
too lies inside all floor solids.  If neither succeeds the function returns None so the
caller can supply a safe fallback.
"""
from __future__ import annotations

import math
from typing import NamedTuple

from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_EDGE, TopAbs_IN, TopAbs_ON
from OCC.Core.BRepAdaptor import BRepAdaptor_Curve
from OCC.Core.TopoDS import Edge as topods_Edge
from OCC.Core.BRepClass3d import BRepClass3d_SolidClassifier
from OCC.Core.gp import gp_Pnt

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


def _is_inside_solid(cx: float, cy: float, solid, z_test: float) -> bool:
    """
    Return True when (cx, cy, z_test) lies inside or on the surface of solid.

    Uses BRepClass3d_SolidClassifier.  Both TopAbs_IN and TopAbs_ON are
    accepted so that points on the footprint boundary (face midpoints) are
    treated as valid material.
    """
    classifier = BRepClass3d_SolidClassifier(solid)
    classifier.Perform(gp_Pnt(cx, cy, z_test), 1e-3)
    return classifier.State() in (TopAbs_IN, TopAbs_ON)


def _footprint_valid(
    cx: float,
    cy: float,
    half_w: float,
    half_d: float,
    floor_tests: list[tuple],  # list of (solid, z_test) pairs for every floor
) -> bool:
    """
    Return True when the entire core footprint rectangle lies inside solid
    material on **every** floor.

    Checks the center plus the 4 corners of the rectangle (cx±half_w, cy±half_d).
    All 5 sample points must be inside (or on the boundary of) each floor solid.

    A core occupies the full building height, so a position is only valid if no
    part of its rectangular footprint intersects a void on any floor.
    """
    sample_points = [
        (cx, cy),
        (cx - half_w, cy - half_d),
        (cx + half_w, cy - half_d),
        (cx - half_w, cy + half_d),
        (cx + half_w, cy + half_d),
    ]
    for solid, z in floor_tests:
        for px, py in sample_points:
            if not _is_inside_solid(px, py, solid, z):
                return False
    return True


def _snap_to_column_grid(
    px: float,
    py: float,
    column_grid: ColumnGrid,
    floor_tests: list[tuple],  # list of (solid, z_test) pairs for every floor
) -> BuildingCore | None:
    """
    Snap a candidate XY point to the nearest column-grid cell center that lies
    inside the subtracted ground-floor solid.

    Strategy
    --------
    1. Collect all cells sorted by distance from (px, py).
    2. Find the nearest cell whose entire footprint rectangle (center + 4 corners)
       lies inside the solid on **every** floor.
       - If that cell is within the snap threshold: use its center.
       - If it is beyond the threshold: prefer the raw candidate (px, py)
         when its footprint is fully inside all floor solids.
    3. Return None when no valid position can be found at all.
    """
    snap_threshold = 0.5 * min(column_grid.span_x, column_grid.span_y)
    half_w = column_grid.span_x / 2
    half_d = column_grid.span_y / 2

    # Build sorted list of (distance, ix, iy, cell_cx, cell_cy)
    cells: list[tuple[float, int, int, float, float]] = []
    for i in range(len(column_grid.grid_lines_x) - 1):
        cell_cx = column_grid.grid_lines_x[i] + column_grid.span_x / 2
        for j in range(len(column_grid.grid_lines_y) - 1):
            cell_cy = column_grid.grid_lines_y[j] + column_grid.span_y / 2
            d = math.sqrt((px - cell_cx) ** 2 + (py - cell_cy) ** 2)
            cells.append((d, i, j, cell_cx, cell_cy))
    cells.sort()

    # Walk cells in distance order; stop at first whose full footprint is valid
    valid_cell: tuple[float, int, int, float, float] | None = None
    for entry in cells:
        d, i, j, cell_cx, cell_cy = entry
        if _footprint_valid(cell_cx, cell_cy, half_w, half_d, floor_tests):
            valid_cell = entry
            break

    if valid_cell is None:
        # No column-grid cell fits fully inside solid material across all floors
        return None

    best_d, best_ix, best_iy, best_cx, best_cy = valid_cell

    if best_d <= snap_threshold:
        # Nearest valid cell is close enough — snap to it
        center_x, center_y = best_cx, best_cy
    else:
        # Nearest valid cell is far — prefer raw candidate if footprint fully valid
        if _footprint_valid(px, py, half_w, half_d, floor_tests):
            center_x, center_y = px, py
        else:
            # Raw candidate footprint clips a void; use the nearest valid cell
            center_x, center_y = best_cx, best_cy

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
    ValueError   if the footprint has no edges or no valid seed position exists.
    RuntimeError if the placement loop fails to converge.
    """
    if not mass.floors:
        raise ValueError("BuildingMass has no floors")

    face_midpoints = _extract_face_midpoints(mass.floors[0].polygon_wire)
    if not face_midpoints:
        raise ValueError("Ground-floor polygon wire has no edges")

    # Build (solid, z_test) pairs for every floor so that core positions are
    # validated against the full building height, not just the ground floor.
    floor_tests = [
        (floor.solid, floor.elevation + floor.floor_height / 2)
        for floor in mass.floors
    ]

    cores: list[BuildingCore] = []

    # Step 1: seed with the footprint centroid
    cx, cy = _polygon_centroid(face_midpoints)
    seed = _snap_to_column_grid(cx, cy, column_grid, floor_tests)

    if seed is None:
        # Centroid fell inside a void — try each face midpoint as a fallback seed,
        # sorted from most central to most peripheral (closest to centroid first).
        candidates = sorted(face_midpoints, key=lambda f: math.sqrt((f.x - cx) ** 2 + (f.y - cy) ** 2))
        for fm in candidates:
            seed = _snap_to_column_grid(fm.x, fm.y, column_grid, floor_tests)
            if seed is not None:
                break

    if seed is None:
        raise ValueError(
            "Building core placement failed: no valid position found inside the "
            "subtracted building mass on all floors. The footprint may be fully subtracted."
        )

    cores.append(seed)

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
        core = _snap_to_column_grid(
            farthest.x, farthest.y, column_grid, floor_tests
        )
        if core is None:
            # Defensive fallback: face midpoints are on the solid boundary so
            # _snap_to_column_grid should never return None here.  Place at raw
            # midpoint with index 0,0 to guarantee progress.
            core = BuildingCore(
                center_x=farthest.x,
                center_y=farthest.y,
                width=column_grid.span_x,
                depth=column_grid.span_y,
                column_ix=0,
                column_iy=0,
            )

        cores.append(core)
        iterations += 1

    return cores
