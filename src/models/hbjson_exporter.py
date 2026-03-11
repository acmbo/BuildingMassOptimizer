"""
HBJson (Honeybee JSON) exporter.

Converts a BuildingMass into a .hbjson file that can be loaded by Ladybug
Tools for Radiance-based daylight simulation.

Public API
----------
export_to_hbjson(mass, output_path, *, identifier, display_name, tolerance, units) -> dict
    Write the building mass as a .hbjson file and return the serialised dict.
"""
from __future__ import annotations

import json
import math
import re
import warnings
from dataclasses import dataclass, field
from typing import Optional

from OCC.Core.BRep import BRep_Tool
from OCC.Core.BRepBndLib import brepbndlib
from OCC.Core.BRepTools import breptools, BRepTools_WireExplorer
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.TopAbs import TopAbs_FACE
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopoDS import topods

from models.building_mass import BuildingMass


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Vertex = tuple[float, float, float]
_Normal = tuple[float, float, float]


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------

@dataclass
class _RawFace:
    """Geometry and classification for one planar face of a floor solid."""
    vertices: list[Vertex]    # CCW when viewed from outside (outward-normal side)
    normal: _Normal           # unit outward normal
    face_type: str            # "Wall" | "Floor" | "RoofCeiling"


@dataclass
class _PendingFace:
    """A face that may still receive an adjacency assignment."""
    raw: _RawFace
    room_id: str
    face_id: str
    adj_face_id: Optional[str] = field(default=None)
    adj_room_id: Optional[str] = field(default=None)


# ---------------------------------------------------------------------------
# Identifier helpers
# ---------------------------------------------------------------------------

_ID_ILLEGAL = re.compile(r"[^.A-Za-z0-9_-]")


def _sanitise_id(s: str) -> str:
    """Replace illegal characters with '_' and truncate to 100 characters."""
    return _ID_ILLEGAL.sub("_", s)[:100]


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _cross(a: _Normal, b: _Normal) -> _Normal:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _normalise(v: _Normal) -> _Normal:
    mag = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if mag < 1e-12:
        return (0.0, 0.0, 1.0)
    return (v[0] / mag, v[1] / mag, v[2] / mag)


def _compute_normal(pts: list[Vertex]) -> _Normal:
    """Unit outward normal from the first triangle of a polygon (right-hand rule)."""
    v0 = (pts[1][0] - pts[0][0], pts[1][1] - pts[0][1], pts[1][2] - pts[0][2])
    v1 = (pts[2][0] - pts[0][0], pts[2][1] - pts[0][1], pts[2][2] - pts[0][2])
    return _normalise(_cross(v0, v1))


def _centroid(pts: list[Vertex]) -> Vertex:
    n = len(pts)
    return (
        sum(p[0] for p in pts) / n,
        sum(p[1] for p in pts) / n,
        sum(p[2] for p in pts) / n,
    )


def _distance(a: Vertex, b: Vertex) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _classify_face_type(normal: _Normal) -> str:
    """Classify a face as Wall, Floor, or RoofCeiling from its outward normal."""
    if normal[2] < -0.9:
        return "Floor"
    if normal[2] > 0.9:
        return "RoofCeiling"
    return "Wall"


def _vertices_from_wire(wire) -> list[Vertex]:
    """Traverse a wire and return one (x, y, z) tuple per edge start-vertex."""
    pts: list[Vertex] = []
    exp = BRepTools_WireExplorer(wire)
    while exp.More():
        p = BRep_Tool.Pnt(exp.CurrentVertex())
        pts.append((p.X(), p.Y(), p.Z()))
        exp.Next()
    return pts


def _solid_centroid(solid) -> Vertex:
    """Return the centroid of the axis-aligned bounding box of a solid."""
    bbox = Bnd_Box()
    brepbndlib.Add(solid, bbox)
    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
    return ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0, (zmin + zmax) / 2.0)


def _dot(a: _Normal, b: _Normal) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


# ---------------------------------------------------------------------------
# Face extraction
# ---------------------------------------------------------------------------

def _extract_faces(solid) -> list[_RawFace]:
    """
    Extract all planar faces from an OCC solid as _RawFace objects.

    Steps for each face:
    1. Cast to TopoDS_Face and get its outer wire via breptools.OuterWire.
    2. Extract vertices with BRepTools_WireExplorer.
    3. Compute the normal from the cross product of the first triangle.
    4. Check outward direction: compare the normal against the vector from the
       solid's bbox centroid to the face centroid.  If the dot product is
       negative the normal points inward → reverse the vertex list.
    5. Classify the face type from the corrected outward normal.

    Using the centroid direction (rather than the OCC orientation flag) is more
    robust: the orientation flag of a face within a solid is not always the
    TopAbs_REVERSED you might expect, and it changes subtly depending on how
    OCC internally builds the shell.

    Faces with fewer than 3 vertices are discarded with a warning (can occur
    on degenerate edges produced by Boolean cuts).
    """
    solid_center = _solid_centroid(solid)
    faces: list[_RawFace] = []

    exp = TopExp_Explorer(solid, TopAbs_FACE)
    while exp.More():
        face = topods.Face(exp.Current())
        outer_wire = breptools.OuterWire(face)
        pts = _vertices_from_wire(outer_wire)

        if len(pts) < 3:
            warnings.warn(
                f"Skipping degenerate face with {len(pts)} vertices.",
                stacklevel=2,
            )
            exp.Next()
            continue

        normal = _compute_normal(pts)
        fc = _centroid(pts)
        to_face = (fc[0] - solid_center[0], fc[1] - solid_center[1], fc[2] - solid_center[2])

        # If normal points toward the solid interior, reverse vertex order
        if _dot(normal, to_face) < 0:
            pts = list(reversed(pts))
            normal = _compute_normal(pts)

        faces.append(_RawFace(
            vertices=pts,
            normal=normal,
            face_type=_classify_face_type(normal),
        ))
        exp.Next()

    return faces


# ---------------------------------------------------------------------------
# Adjacency pairing
# ---------------------------------------------------------------------------

def _pair_adjacencies(
    pending_by_floor: list[list[_PendingFace]],
    tolerance: float,
) -> None:
    """
    Mutate _PendingFace objects in-place to fill adj_face_id / adj_room_id for
    every ceiling/floor pair between neighbouring floors.

    Matching uses centroid proximity within `tolerance`.  Unmatched faces keep
    adj_face_id = None and receive an Outdoors boundary condition later.
    """
    for i in range(len(pending_by_floor) - 1):
        ceilings = [pf for pf in pending_by_floor[i] if pf.raw.face_type == "RoofCeiling"]
        floors_above = [pf for pf in pending_by_floor[i + 1] if pf.raw.face_type == "Floor"]

        for cf in ceilings:
            cc = _centroid(cf.raw.vertices)
            for ff in floors_above:
                if _distance(cc, _centroid(ff.raw.vertices)) < tolerance:
                    cf.adj_face_id = ff.face_id
                    cf.adj_room_id = ff.room_id
                    ff.adj_face_id = cf.face_id
                    ff.adj_room_id = cf.room_id
                    break


# ---------------------------------------------------------------------------
# JSON dict builders
# ---------------------------------------------------------------------------

def _bc_outdoors() -> dict:
    return {"type": "Outdoors", "sun_exposure": True, "wind_exposure": True}


def _bc_ground() -> dict:
    return {"type": "Ground"}


def _bc_surface(adj_face_id: str, adj_room_id: str) -> dict:
    return {
        "type": "Surface",
        "boundary_condition_objects": [adj_face_id, adj_room_id],
    }


def _build_face_dict(pf: _PendingFace, is_ground_floor: bool) -> dict:
    """
    Build the Face JSON dict for one _PendingFace.

    Boundary condition logic:
    - Floor face on ground floor  → Ground
    - Face with a matched adjacency → Surface (bidirectional)
    - Everything else               → Outdoors
    """
    raw = pf.raw

    if raw.face_type == "Floor" and is_ground_floor:
        bc = _bc_ground()
    elif pf.adj_face_id is not None:
        bc = _bc_surface(pf.adj_face_id, pf.adj_room_id)
    else:
        bc = _bc_outdoors()

    return {
        "type": "Face",
        "identifier": pf.face_id,
        "geometry": {
            "type": "Face3D",
            "boundary": [list(v) for v in raw.vertices],
        },
        "face_type": raw.face_type,
        "boundary_condition": bc,
        "properties": {
            "type": "FacePropertiesAbridged",
            "radiance": {"type": "FaceRadiancePropertiesAbridged"},
        },
    }


def _build_room_dict(
    floor_index: int,
    room_id: str,
    pending_faces: list[_PendingFace],
    is_ground_floor: bool,
) -> dict:
    return {
        "type": "Room",
        "identifier": room_id,
        "display_name": f"Floor {floor_index}",
        "story": f"floor_{floor_index:03d}",
        "multiplier": 1,
        "faces": [_build_face_dict(pf, is_ground_floor) for pf in pending_faces],
        "properties": {
            "type": "RoomPropertiesAbridged",
            "radiance": {"type": "RoomRadiancePropertiesAbridged"},
        },
    }


def _build_model_dict(
    rooms: list[dict],
    model_id: str,
    display_name: Optional[str],
    tolerance: float,
    units: str,
) -> dict:
    model: dict = {
        "type": "Model",
        "identifier": model_id,
        "version": "0.0.0",
        "units": units,
        "tolerance": tolerance,
        "angle_tolerance": 1.0,
        "rooms": rooms,
        "properties": {
            "type": "ModelProperties",
            "radiance": {"type": "ModelRadianceProperties"},
        },
    }
    if display_name is not None:
        model["display_name"] = display_name
    return model


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_to_hbjson(
    mass: BuildingMass,
    output_path: str,
    *,
    identifier: str = "BuildingMass",
    display_name: Optional[str] = None,
    tolerance: float = 0.01,
    units: str = "Meters",
) -> dict:
    """
    Export a BuildingMass to a Honeybee JSON (.hbjson) file.

    Each FloorData becomes one Room.  Faces are extracted from OCC solids,
    classified by outward normal, and assigned boundary conditions including
    bidirectional Surface adjacency between adjacent floors.

    Parameters
    ----------
    mass : BuildingMass
        The building mass to export (plain or subtracted).
    output_path : str
        Destination file path (e.g. "/tmp/building.hbjson").
    identifier : str
        Model-level identifier.  Sanitised to ``[.A-Za-z0-9_-]{1,100}``.
    display_name : str | None
        Optional human-readable model name written to the file.
    tolerance : float
        Geometric tolerance in metres; also used for centroid-proximity
        matching when pairing adjacent floor/ceiling faces.
    units : str
        Unit system string for the HBJson file, e.g. ``"Meters"``.

    Returns
    -------
    dict
        The serialised model dict — identical in content to the written file.

    Raises
    ------
    ValueError
        If ``mass`` has no floors.
    OSError
        If ``output_path`` cannot be opened for writing.
    """
    if not mass.floors:
        raise ValueError("BuildingMass has no floors — nothing to export.")

    model_id = _sanitise_id(identifier)

    # ------------------------------------------------------------------
    # Step 1: Extract faces from every floor solid
    # ------------------------------------------------------------------
    pending_by_floor: list[list[_PendingFace]] = []

    for floor in mass.floors:
        room_id = f"{model_id}_floor_{floor.index:03d}"
        raw_faces = _extract_faces(floor.solid)
        pending = [
            _PendingFace(raw=rf, room_id=room_id, face_id=f"{room_id}_face_{n:03d}")
            for n, rf in enumerate(raw_faces)
        ]
        pending_by_floor.append(pending)

    # ------------------------------------------------------------------
    # Step 2: Pair adjacent ceiling / floor faces
    # ------------------------------------------------------------------
    _pair_adjacencies(pending_by_floor, tolerance)

    # ------------------------------------------------------------------
    # Step 3: Build room dicts
    # ------------------------------------------------------------------
    rooms = [
        _build_room_dict(
            floor.index,
            f"{model_id}_floor_{floor.index:03d}",
            pending,
            is_ground_floor=(floor.index == 0),
        )
        for floor, pending in zip(mass.floors, pending_by_floor)
    ]

    # ------------------------------------------------------------------
    # Step 4: Assemble model dict and write file
    # ------------------------------------------------------------------
    model_dict = _build_model_dict(rooms, model_id, display_name, tolerance, units)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(model_dict, f, indent=2)

    return model_dict
