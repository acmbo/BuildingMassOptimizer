"""
Subtractive form generation engine.

Public API:
    apply_subtractions(mass, config) -> BuildingMass
    extract_bottom_wire(solid, elevation) -> TopoDS_Shape

Internal helpers (also importable for unit testing):
    _validate_plan_size(s, config) -> Subtractor | None
    _validate_vertical(s, total_height, config) -> Subtractor | None
    _validate_horizontal(s, floor_height, total_height, config) -> Subtractor | None
"""
from __future__ import annotations

from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCC.Core.BRepCheck import BRepCheck_Analyzer
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_WIRE
from OCC.Core.BRepBndLib import brepbndlib
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRep import BRep_Builder
from OCC.Core.TopoDS import TopoDS_Compound
from OCC.Core.gp import gp_Pnt

from models.subtractor import Subtractor, SubtractorType, SubtractionConfig
from models.building_mass import BuildingMass
from models.floor_data import FloorData


# ---------------------------------------------------------------------------
# Constraint helpers
# ---------------------------------------------------------------------------

def _validate_plan_size(s: Subtractor, config: SubtractionConfig) -> Subtractor | None:
    """
    Clip oversized plan dimensions to max_plan_size; deactivate if any
    resulting dimension falls below min_plan_size.

    Returns the (possibly modified) Subtractor, or None if deactivated.
    """
    width = min(s.width, config.max_plan_size)
    depth = min(s.depth, config.max_plan_size)

    if width < config.min_plan_size or depth < config.min_plan_size:
        return None  # deactivated

    if width == s.width and depth == s.depth:
        return s  # nothing changed — return same instance

    return Subtractor(s.x, s.y, width, depth, s.z_bottom, s.z_top, s.subtractor_type)


def _validate_vertical(
    s: Subtractor,
    total_height: float,
    config: SubtractionConfig,
) -> Subtractor | None:
    """
    Snap vertical subtractor faces to building top/bottom if within the
    snap threshold. Deactivate if neither face qualifies.

    Returns the (possibly modified) Subtractor, or None if deactivated.
    """
    threshold = config.vertical_snap_threshold * total_height

    gap_bottom = s.z_bottom             # distance from building bottom (z=0)
    gap_top = total_height - s.z_top    # distance from building top

    snapped_bottom = gap_bottom < threshold
    snapped_top = gap_top < threshold

    if not (snapped_bottom or snapped_top):
        return None  # deactivated: neither face is close enough to the boundary

    z_bottom = 0.0 if snapped_bottom else s.z_bottom
    z_top = total_height if snapped_top else s.z_top

    if z_bottom == s.z_bottom and z_top == s.z_top:
        return s

    return Subtractor(s.x, s.y, s.width, s.depth, z_bottom, z_top, s.subtractor_type)


def _validate_horizontal(
    s: Subtractor,
    floor_height: float,
    total_height: float,
    config: SubtractionConfig,
) -> Subtractor | None:
    """
    Enforce the horizontal subtractor height constraint:
        floor_height <= (z_top - z_bottom) < horizontal_max_height_ratio * total_height

    Too-tall subtractors are clipped. Too-short ones are deactivated.

    Returns the (possibly modified) Subtractor, or None if deactivated.
    """
    height = s.z_top - s.z_bottom
    max_height = config.horizontal_max_height_ratio * total_height

    if height < floor_height:
        return None  # deactivated: height below minimum (1 floor)

    if height >= max_height:
        # Clip: keep z_bottom fixed, pull z_top down
        z_top = s.z_bottom + max_height
        return Subtractor(s.x, s.y, s.width, s.depth, s.z_bottom, z_top, s.subtractor_type)

    return s  # within range, unchanged


def _apply_boundary_constraint(
    s: Subtractor,
    bldg_xmin: float,
    bldg_ymin: float,
    bldg_xmax: float,
    bldg_ymax: float,
    config: SubtractionConfig,
) -> Subtractor:
    """
    Apply the boundary constraint to a vertical subtractor:
      - Enabled  (closed): clip subtractor to stay inside the building footprint AABB.
      - Disabled (open):   snap faces close to the outer wall outward through it.

    Returns the (possibly modified) Subtractor.
    """
    bldg_width = bldg_xmax - bldg_xmin
    bldg_depth = bldg_ymax - bldg_ymin
    snap_x = config.boundary_snap_fraction * bldg_width
    snap_y = config.boundary_snap_fraction * bldg_depth

    x, y, width, depth = s.x, s.y, s.width, s.depth

    if config.boundary_constraint_enabled:
        # Push inward: clip to building AABB
        x = max(x, bldg_xmin)
        y = max(y, bldg_ymin)
        x_end = min(x + width, bldg_xmax)
        y_end = min(y + depth, bldg_ymax)
        width = x_end - x
        depth = y_end - y
    else:
        # Push outward: snap faces close to the boundary through the wall
        if abs(x - bldg_xmin) < snap_x:
            x = bldg_xmin
        if abs((x + width) - bldg_xmax) < snap_x:
            width = bldg_xmax - x
        if abs(y - bldg_ymin) < snap_y:
            y = bldg_ymin
        if abs((y + depth) - bldg_ymax) < snap_y:
            depth = bldg_ymax - y

    if x == s.x and y == s.y and width == s.width and depth == s.depth:
        return s

    return Subtractor(x, y, width, depth, s.z_bottom, s.z_top, s.subtractor_type)


# ---------------------------------------------------------------------------
# OCC geometry helpers
# ---------------------------------------------------------------------------

def _build_box(s: Subtractor):
    """Construct the OCC cutting solid for a subtractor."""
    return BRepPrimAPI_MakeBox(
        gp_Pnt(s.x, s.y, s.z_bottom),
        gp_Pnt(s.x + s.width, s.y + s.depth, s.z_top),
    ).Shape()


def extract_bottom_wire(solid, elevation: float):
    """
    Extract the plan outline wire(s) at the bottom face of a floor solid.

    Iterates all faces of the solid, selects every horizontal face at
    z ≈ elevation, and collects all their wires (outer boundary + any inner
    holes such as atriums or through-holes).

    Returns:
        A single TopoDS_Wire if exactly one wire is found, or a
        TopoDS_Compound of multiple wires if the face has holes or was split.

    Raises:
        ValueError if no face at the given elevation can be found.
    """
    tol = 1e-2
    wires = []

    face_exp = TopExp_Explorer(solid, TopAbs_FACE)
    while face_exp.More():
        face = face_exp.Current()

        bbox = Bnd_Box()
        brepbndlib.Add(face, bbox)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()

        # A horizontal face at the given elevation has zmin ≈ zmax ≈ elevation
        if abs(zmin - elevation) < tol and abs(zmax - elevation) < tol:
            wire_exp = TopExp_Explorer(face, TopAbs_WIRE)
            while wire_exp.More():
                wires.append(wire_exp.Current())
                wire_exp.Next()

        face_exp.Next()

    if not wires:
        raise ValueError(
            f"extract_bottom_wire: no horizontal face found at elevation {elevation}"
        )

    if len(wires) == 1:
        return wires[0]

    # Multiple wires (e.g. outer boundary + inner holes) → pack into a compound
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for w in wires:
        builder.Add(compound, w)
    return compound


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def apply_subtractions(mass: BuildingMass, config: SubtractionConfig) -> BuildingMass:
    """
    Apply all subtractors in config to mass and return a new BuildingMass.

    Step 1 – Validate and clamp each subtractor.
    Step 2 – Build OCC cutting boxes for all active subtractors.
    Step 3 – For each floor, apply all overlapping subtractor boxes via
             sequential boolean cuts.
    Step 4 – Rebuild and return a new BuildingMass with updated floor geometry.
    """
    total_height = mass.total_height
    floor_height = mass.floor_height

    # Building footprint bounds (from polygon points, not AABB with OCC tolerance)
    xs = [p[0] for p in mass.polygon_points]
    ys = [p[1] for p in mass.polygon_points]
    bldg_xmin, bldg_xmax = min(xs), max(xs)
    bldg_ymin, bldg_ymax = min(ys), max(ys)

    # ------------------------------------------------------------------
    # Step 1+2: Validate subtractors and build cutting boxes
    # ------------------------------------------------------------------
    active: list[tuple[Subtractor, object]] = []  # (validated_subtractor, occ_box)

    for s in config.vertical_subtractors:
        s = _validate_plan_size(s, config)
        if s is None:
            continue
        s = _validate_vertical(s, total_height, config)
        if s is None:
            continue
        s = _apply_boundary_constraint(
            s, bldg_xmin, bldg_ymin, bldg_xmax, bldg_ymax, config
        )
        active.append((s, _build_box(s)))

    for s in config.horizontal_subtractors:
        s = _validate_plan_size(s, config)
        if s is None:
            continue
        s = _validate_horizontal(s, floor_height, total_height, config)
        if s is None:
            continue
        # Boundary constraint applies only to vertical subtractors per requirements
        active.append((s, _build_box(s)))

    # ------------------------------------------------------------------
    # Step 3: Process each floor
    # ------------------------------------------------------------------
    new_floors: list[FloorData] = []

    for floor in mass.floors:
        floor_z_min = floor.elevation
        floor_z_max = floor.elevation + floor.floor_height

        # Collect all cutting boxes whose Z range overlaps this floor
        floor_boxes = [
            box
            for (sub, box) in active
            if sub.z_bottom < floor_z_max and sub.z_top > floor_z_min
        ]

        if not floor_boxes:
            # No subtractors affect this floor → keep original floor unchanged
            new_floors.append(floor)
            continue

        # Apply sequential boolean cuts
        result_solid = floor.solid
        for sub_box in floor_boxes:
            cut = BRepAlgoAPI_Cut(result_solid, sub_box)
            if cut.IsDone() and not cut.Shape().IsNull():
                analyzer = BRepCheck_Analyzer(cut.Shape())
                if analyzer.IsValid():
                    result_solid = cut.Shape()
                # else: silently skip this subtractor for this floor (req. 4.4)

        # Extract updated polygon wire from cut solid
        try:
            new_wire = extract_bottom_wire(result_solid, floor.elevation)
        except ValueError:
            new_wire = floor.polygon_wire  # fallback: keep original wire

        new_floors.append(FloorData(
            index=floor.index,
            elevation=floor.elevation,
            floor_height=floor.floor_height,
            solid=result_solid,
            polygon_wire=new_wire,
        ))

    # ------------------------------------------------------------------
    # Step 4: Return new BuildingMass
    # ------------------------------------------------------------------
    return BuildingMass(
        polygon_points=mass.polygon_points,
        floor_height=mass.floor_height,
        num_floors=mass.num_floors,
        floors=new_floors,
    )
