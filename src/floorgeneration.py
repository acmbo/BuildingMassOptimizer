from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCC.Core.BRepBuilderAPI import (
    BRepBuilderAPI_MakePolygon,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_Transform,
)
from OCC.Core.gp import gp_Pnt, gp_Vec, gp_Trsf


def create_wire(points, z_offset: float = 0.0):
    """
    Build a closed polygon wire from a list of (x, y, z) points.
    If z_offset is given, the Z component of every point is overridden with it,
    which is useful when placing a floor outline at a specific elevation.
    """
    poly = BRepBuilderAPI_MakePolygon()
    for p in points:
        z = z_offset if z_offset != 0.0 else p[2]
        poly.Add(gp_Pnt(p[0], p[1], z))
    poly.Close()
    return poly.Wire()


def create_polygon(points):
    """Create a planar face from a list of (x, y, z) points."""
    wire = create_wire(points)
    face = BRepBuilderAPI_MakeFace(wire)
    return face.Shape()


def translate_shape(shape, dz):
    """Return a copy of shape translated by dz along Z."""
    trsf = gp_Trsf()
    trsf.SetTranslation(gp_Vec(0, 0, dz))
    return BRepBuilderAPI_Transform(shape, trsf, True).Shape()


def extrude_face(face, height):
    """Extrude a face upward by height along Z."""
    return BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, height)).Shape()
