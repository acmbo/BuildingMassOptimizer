"""
OCC wire geometry extraction utilities.

Public API
----------
extract_wire_loops(wire_shape) -> list[list[tuple[float, float, float]]]
    Extract ordered (x, y, z) vertex lists from a TopoDS_Wire or a
    TopoDS_Compound of wires (as returned by extract_bottom_wire() for floors
    with interior voids after subtraction).
"""
from __future__ import annotations

from OCC.Core.BRep import BRep_Tool
from OCC.Core.BRepTools import BRepTools_WireExplorer
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_WIRE, TopAbs_ShapeEnum
from OCC.Core.TopoDS import topods


def _points_from_wire(wire) -> list[tuple[float, float, float]]:
    """
    Return one (x, y, z) tuple per edge start-vertex in the wire, in order.

    Uses BRepTools_WireExplorer which guarantees edge ordering — i.e. the
    end vertex of edge i is the start vertex of edge i+1.  The returned list
    implicitly closes back to pts[0].
    """
    pts: list[tuple[float, float, float]] = []
    exp = BRepTools_WireExplorer(wire)
    while exp.More():
        v = exp.CurrentVertex()
        p = BRep_Tool.Pnt(v)
        pts.append((p.X(), p.Y(), p.Z()))
        exp.Next()
    return pts


def extract_wire_loops(
    wire_shape,
) -> list[list[tuple[float, float, float]]]:
    """
    Extract ordered vertex lists from a wire or compound of wires.

    Parameters
    ----------
    wire_shape
        A ``TopoDS_Wire`` (single closed polygon) or a ``TopoDS_Compound``
        containing multiple wires (outer boundary + interior holes).
        This is exactly the type returned by ``extract_bottom_wire()``.

    Returns
    -------
    list[list[tuple[float, float, float]]]
        One inner list per loop.  The first loop is the outer boundary;
        any subsequent loops are interior holes (courtyards, atriums).
        Each loop contains one vertex per edge; the polygon is implicitly
        closed — the last vertex connects back to the first.

    Notes
    -----
    The function inspects ``wire_shape.ShapeType()`` to decide how to
    iterate:

    * ``TopAbs_WIRE``     → single loop, returned directly.
    * Any container shape → ``TopExp_Explorer`` finds all nested wires.
    """
    loops: list[list[tuple[float, float, float]]] = []

    if wire_shape.ShapeType() == TopAbs_WIRE:
        pts = _points_from_wire(topods.Wire(wire_shape))
        if pts:
            loops.append(pts)
    else:
        exp = TopExp_Explorer(wire_shape, TopAbs_WIRE)
        while exp.More():
            pts = _points_from_wire(topods.Wire(exp.Current()))
            if pts:
                loops.append(pts)
            exp.Next()

    return loops
