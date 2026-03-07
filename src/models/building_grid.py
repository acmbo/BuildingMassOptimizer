from __future__ import annotations

import math
from dataclasses import dataclass, field

from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib
from OCC.Core.BRep import BRep_Builder
from OCC.Core.TopoDS import TopoDS_Compound

from models.building_mass import BuildingMass
from models.cell_mode import CellMode
from models.grid_cell import GridCell


@dataclass
class BuildingGrid:
    """
    Regular 3D grid aligned to the AABB of a BuildingMass.

    Cells are floor-aligned in Z (each cell height == floor_height).
    X and Y cell sizes are derived from the AABB and the chosen CellMode.

    Create via the classmethod:
        grid = BuildingGrid.create(mass, CellMode.FIXED_SIZE, cell_size=2.0)
        grid = BuildingGrid.create(mass, CellMode.CELL_COUNT, cell_count=10)
    """

    building_mass: BuildingMass

    cell_mode: CellMode
    """Strategy used to resolve cell_size."""

    cell_size: float
    """Resolved nominal cell size (input for FIXED_SIZE; derived for CELL_COUNT)."""

    aabb_min: tuple[float, float, float]
    """Minimum corner of the bounding box."""

    aabb_max: tuple[float, float, float]
    """Maximum corner of the bounding box."""

    nx: int
    """Number of cells along X."""

    ny: int
    """Number of cells along Y."""

    nz: int
    """Number of cells along Z (== num_floors)."""

    cell_size_x: float
    """Actual cell width in X (AABB width / nx)."""

    cell_size_y: float
    """Actual cell depth in Y (AABB depth / ny)."""

    cell_size_z: float
    """Cell height in Z (== floor_height)."""

    cells: list[GridCell]
    """All cells in row-major order (iz, iy, ix)."""

    total_cells: int = field(init=False)
    """Derived total cell count (nx × ny × nz)."""

    def __post_init__(self) -> None:
        self.total_cells = self.nx * self.ny * self.nz

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        building_mass: BuildingMass,
        cell_mode: CellMode,
        cell_size: float | None = None,
        cell_count: int | None = None,
    ) -> BuildingGrid:
        """
        Generate a BuildingGrid from a BuildingMass.

        Parameters
        ----------
        building_mass : BuildingMass
        cell_mode     : CellMode.FIXED_SIZE or CellMode.CELL_COUNT
        cell_size     : required for FIXED_SIZE — absolute cell length in model units
        cell_count    : required for CELL_COUNT — number of cells along the longest axis
        """
        if cell_mode == CellMode.FIXED_SIZE:
            if cell_size is None or cell_size <= 0:
                raise ValueError(
                    "cell_size must be a positive number when cell_mode is FIXED_SIZE"
                )
        elif cell_mode == CellMode.CELL_COUNT:
            if cell_count is None or cell_count < 1:
                raise ValueError(
                    "cell_count must be >= 1 when cell_mode is CELL_COUNT"
                )
        else:
            raise ValueError(f"Unknown cell_mode: {cell_mode}")

        # --- AABB via OCC brepbndlib on all floor solids ---
        compound = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(compound)
        for floor in building_mass.floors:
            builder.Add(compound, floor.solid)

        bbox = Bnd_Box()
        brepbndlib.Add(compound, bbox)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()

        aabb_min = (xmin, ymin, zmin)
        aabb_max = (xmax, ymax, zmax)

        width = xmax - xmin
        depth = ymax - ymin

        # --- Resolve cell_size ---
        if cell_mode == CellMode.CELL_COUNT:
            cell_size = max(width, depth) / cell_count

        # --- Grid dimensions ---
        nx = math.ceil(width / cell_size)
        ny = math.ceil(depth / cell_size)
        nz = building_mass.num_floors

        # Actual cell sizes (distribute AABB evenly so cells tile exactly)
        cell_size_x = width / nx
        cell_size_y = depth / ny
        cell_size_z = building_mass.floor_height

        # --- Build cells in row-major order (iz, iy, ix) ---
        cells: list[GridCell] = []
        for iz in range(nz):
            for iy in range(ny):
                for ix in range(nx):
                    min_pt = (
                        xmin + ix * cell_size_x,
                        ymin + iy * cell_size_y,
                        zmin + iz * cell_size_z,
                    )
                    max_pt = (
                        xmin + (ix + 1) * cell_size_x,
                        ymin + (iy + 1) * cell_size_y,
                        zmin + (iz + 1) * cell_size_z,
                    )
                    cells.append(GridCell(ix=ix, iy=iy, iz=iz, min_pt=min_pt, max_pt=max_pt))

        return cls(
            building_mass=building_mass,
            cell_mode=cell_mode,
            cell_size=cell_size,
            aabb_min=aabb_min,
            aabb_max=aabb_max,
            nx=nx,
            ny=ny,
            nz=nz,
            cell_size_x=cell_size_x,
            cell_size_y=cell_size_y,
            cell_size_z=cell_size_z,
            cells=cells,
        )

    # ------------------------------------------------------------------
    # Access helpers
    # ------------------------------------------------------------------

    def get_cell(self, ix: int, iy: int, iz: int) -> GridCell:
        """Return the cell at grid position (ix, iy, iz)."""
        return self.cells[iz * self.ny * self.nx + iy * self.nx + ix]

    def cells_at_floor(self, iz: int) -> list[GridCell]:
        """Return all cells belonging to a single floor level."""
        return [c for c in self.cells if c.iz == iz]

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"BuildingGrid("
            f"nx={self.nx}, ny={self.ny}, nz={self.nz}, "
            f"total_cells={self.total_cells}, "
            f"cell_size_x={self.cell_size_x:.3f}, "
            f"cell_size_y={self.cell_size_y:.3f}, "
            f"cell_size_z={self.cell_size_z:.3f})"
        )
