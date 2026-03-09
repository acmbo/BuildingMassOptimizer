from __future__ import annotations

import random
from dataclasses import dataclass

from models.building_mass import BuildingMass
from models.subtractor import Subtractor, SubtractorType, SubtractionConfig
from models.subtraction_engine import apply_subtractions
from models.column_grid import ColumnGrid
from models.span_mode import SpanMode
from models.building_core_engine import find_building_cores


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GENES_PER_SUBTRACTOR: int = 6
"""Number of genome genes that encode one subtractor."""


# ---------------------------------------------------------------------------
# Initialization parameters
# ---------------------------------------------------------------------------

@dataclass
class IndividuumParams:
    """
    Fixed initialization parameters for one evolutionary optimization run.

    These are set once by the architect and remain constant throughout
    the optimization. The EA only modifies the *optimization parameters*
    (genome values inside Individuum).

    Attributes
    ----------
    polygon_points
        Footprint vertices in the XY plane (z values are ignored).
    floor_height
        Uniform floor-to-floor height in model units (metres).
    num_floors
        Total number of floors in the maximal volume.
    n_vertical
        Number of vertical subtractors (courtyards, atriums, notches).
    n_horizontal
        Number of horizontal subtractors (stilts, empty floors, cascades).
    span_x
        Column grid spacing along X in model units.
    span_y
        Column grid spacing along Y in model units.
    min_plan_spans
        Minimum subtractor plan size expressed in column-grid spans.
        Subtractors smaller than this are deactivated during constraint
        application (via min_plan_size → SubtractionConfig).
    max_plan_spans
        Maximum subtractor plan size in column-grid spans.
        Subtractors larger than this are clipped.
    boundary_constraint_enabled
        True  → closed boundary: vertical subtractor faces stay inside,
                producing enclosed interior voids (courtyards / atriums).
        False → open boundary: faces close to the outer wall snap
                outward through it (notches / slots).
    boundary_snap_fraction
        Fraction of building width/depth within which a face is considered
        "close" to the outer boundary (default 0.10).
    vertical_snap_threshold
        Fraction of total_height within which a vertical subtractor face
        snaps to the building top or bottom (default 0.30).
    horizontal_max_height_ratio
        Max allowed vertical extent of a horizontal subtractor as a
        fraction of total_height (default 0.30).
    """

    polygon_points: list[tuple[float, float, float]]
    floor_height: float
    num_floors: int
    n_vertical: int
    n_horizontal: int
    span_x: float
    span_y: float
    min_plan_spans: float = 2.0
    max_plan_spans: float = 5.0
    boundary_constraint_enabled: bool = True
    boundary_snap_fraction: float = 0.10
    vertical_snap_threshold: float = 0.30
    horizontal_max_height_ratio: float = 0.30
    core_generation_enabled: bool = False
    max_face_distance: float = 35.0

    def __post_init__(self) -> None:
        if self.floor_height <= 0:
            raise ValueError(f"floor_height must be positive, got {self.floor_height}")
        if self.num_floors < 1:
            raise ValueError(f"num_floors must be >= 1, got {self.num_floors}")
        if self.n_vertical < 0:
            raise ValueError(f"n_vertical must be >= 0, got {self.n_vertical}")
        if self.n_horizontal < 0:
            raise ValueError(f"n_horizontal must be >= 0, got {self.n_horizontal}")
        if self.span_x <= 0:
            raise ValueError(f"span_x must be positive, got {self.span_x}")
        if self.span_y <= 0:
            raise ValueError(f"span_y must be positive, got {self.span_y}")
        if self.min_plan_spans <= 0:
            raise ValueError(f"min_plan_spans must be positive, got {self.min_plan_spans}")
        if self.max_plan_spans < self.min_plan_spans:
            raise ValueError(
                f"max_plan_spans ({self.max_plan_spans}) must be >= "
                f"min_plan_spans ({self.min_plan_spans})"
            )

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def genome_length(self) -> int:
        """Total number of genes: (n_vertical + n_horizontal) × GENES_PER_SUBTRACTOR."""
        return (self.n_vertical + self.n_horizontal) * GENES_PER_SUBTRACTOR

    @property
    def total_height(self) -> float:
        """Total building height in model units."""
        return self.floor_height * self.num_floors

    @property
    def bbox_xmin(self) -> float:
        return min(p[0] for p in self.polygon_points)

    @property
    def bbox_xmax(self) -> float:
        return max(p[0] for p in self.polygon_points)

    @property
    def bbox_ymin(self) -> float:
        return min(p[1] for p in self.polygon_points)

    @property
    def bbox_ymax(self) -> float:
        return max(p[1] for p in self.polygon_points)

    @property
    def bbox_width(self) -> float:
        """Footprint extent along X."""
        return self.bbox_xmax - self.bbox_xmin

    @property
    def bbox_depth(self) -> float:
        """Footprint extent along Y."""
        return self.bbox_ymax - self.bbox_ymin

    @property
    def min_plan_size(self) -> float:
        """Minimum subtractor plan size in model units (min_plan_spans × smaller span)."""
        return self.min_plan_spans * min(self.span_x, self.span_y)

    @property
    def max_plan_size(self) -> float:
        """Maximum subtractor plan size in model units (max_plan_spans × larger span)."""
        return self.max_plan_spans * max(self.span_x, self.span_y)


# ---------------------------------------------------------------------------
# Individuum
# ---------------------------------------------------------------------------

@dataclass
class Individuum:
    """
    One building massing design variant for evolutionary optimization.

    The genome is a flat list of normalized floats in [0, 1] encoding
    the raw optimization parameters for all subtractors. During phenotype
    construction (build()), these are denormalized to building coordinates,
    aligned to the structural column grid, and constrained before boolean
    geometry is generated.

    Genome layout — length = (n_vertical + n_horizontal) × 6:

        Vertical subtractors first  (k = 0 … n_vertical - 1)
        Horizontal subtractors next (k = n_vertical … n_vertical + n_horizontal - 1)

        For subtractor k:
            genome[k*6 + 0]  x_norm      → x      = bbox_xmin + x_norm   × bbox_width
            genome[k*6 + 1]  y_norm      → y      = bbox_ymin + y_norm   × bbox_depth
            genome[k*6 + 2]  w_norm      → width  = w_norm × bbox_width
            genome[k*6 + 3]  d_norm      → depth  = d_norm × bbox_depth
            genome[k*6 + 4]  z_bot_norm  → z_bottom = z_bot_norm × total_height
            genome[k*6 + 5]  z_top_norm  → z_top    = z_top_norm × total_height
                                           (swapped if z_top < z_bottom)

    Create via:
        ind = Individuum.create_random(params)
        original_mass, subtracted_mass, config = ind.build()
    """

    params: IndividuumParams
    genome: list[float]

    def __post_init__(self) -> None:
        expected = self.params.genome_length
        if len(self.genome) != expected:
            raise ValueError(
                f"Genome length {len(self.genome)} does not match "
                f"expected {expected} for "
                f"n_vertical={self.params.n_vertical}, "
                f"n_horizontal={self.params.n_horizontal}"
            )
        for i, g in enumerate(self.genome):
            if not (0.0 <= g <= 1.0):
                raise ValueError(f"genome[{i}] = {g!r} is out of range [0, 1]")

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create_random(
        cls,
        params: IndividuumParams,
        rng: random.Random | None = None,
    ) -> Individuum:
        """
        Create a random individuum by sampling uniform [0, 1] for every gene.

        Parameters
        ----------
        params
            Shared initialization parameters.
        rng
            Optional seeded Random instance for reproducibility.
            A fresh Random() (random seed) is used when not supplied.
        """
        if rng is None:
            rng = random.Random()
        genome = [rng.random() for _ in range(params.genome_length)]
        return cls(params=params, genome=genome)

    # ------------------------------------------------------------------
    # Genome decoding
    # ------------------------------------------------------------------

    def _decode_subtractor(self, k: int, sub_type: SubtractorType) -> Subtractor:
        """
        Decode subtractor k from the genome and return a raw Subtractor.

        The returned subtractor has not yet been aligned to the column grid
        or had constraints applied. Those steps happen in build().
        """
        _EPS = 1e-6
        g = self.genome[k * GENES_PER_SUBTRACTOR : (k + 1) * GENES_PER_SUBTRACTOR]
        p = self.params

        x = p.bbox_xmin + g[0] * p.bbox_width
        y = p.bbox_ymin + g[1] * p.bbox_depth
        width = max(g[2] * p.bbox_width, _EPS)
        depth = max(g[3] * p.bbox_depth, _EPS)

        z_a = g[4] * p.total_height
        z_b = g[5] * p.total_height
        z_bottom = min(z_a, z_b)
        z_top = max(z_a, z_b)
        if z_top - z_bottom < _EPS:
            z_top = z_bottom + p.floor_height

        return Subtractor(
            x=x,
            y=y,
            width=width,
            depth=depth,
            z_bottom=z_bottom,
            z_top=z_top,
            subtractor_type=sub_type,
        )

    # ------------------------------------------------------------------
    # Build — full generation pipeline
    # ------------------------------------------------------------------

    def build(self) -> tuple[BuildingMass, BuildingMass, SubtractionConfig]:
        """
        Decode the genome and run the full generation pipeline.

        Steps:
          1. Create maximal BuildingMass
          2. Create ColumnGrid for grid alignment
          3. Decode genome → raw Subtractor objects
          4. Align each subtractor to the nearest quarter-span position
             (deactivates any subtractor that collapses to zero plan size)
          5. Build SubtractionConfig
          6. Apply subtractions (plan-size, vertical/horizontal constraints,
             boundary constraint, boolean cuts)

        Returns
        -------
        original_mass
            The uncut maximal building mass.
        subtracted_mass
            The building mass after all active subtractors are applied.
        config
            The SubtractionConfig used (contains aligned, active subtractors).
        """
        p = self.params

        # 1. Maximal volume
        original_mass = BuildingMass.create(p.polygon_points, p.floor_height, p.num_floors)

        # 2. Column grid
        column_grid = ColumnGrid.create(
            original_mass,
            SpanMode.FIXED_SPAN,
            span_x=p.span_x,
            span_y=p.span_y,
        )

        # 3. Decode raw subtractors
        raw_vertical = [
            self._decode_subtractor(k, SubtractorType.VERTICAL)
            for k in range(p.n_vertical)
        ]
        raw_horizontal = [
            self._decode_subtractor(p.n_vertical + k, SubtractorType.HORIZONTAL)
            for k in range(p.n_horizontal)
        ]

        # 4. Align to column grid (quarter-span snapping)
        aligned_vertical = [
            aligned
            for s in raw_vertical
            if (aligned := column_grid.align_subtractor(s)) is not None
        ]
        aligned_horizontal = [
            aligned
            for s in raw_horizontal
            if (aligned := column_grid.align_subtractor(s)) is not None
        ]

        # 5. Subtraction config
        config = SubtractionConfig(
            vertical_subtractors=aligned_vertical,
            horizontal_subtractors=aligned_horizontal,
            vertical_snap_threshold=p.vertical_snap_threshold,
            horizontal_max_height_ratio=p.horizontal_max_height_ratio,
            min_plan_size=p.min_plan_size,
            max_plan_size=p.max_plan_size,
            boundary_constraint_enabled=p.boundary_constraint_enabled,
            boundary_snap_fraction=p.boundary_snap_fraction,
        )

        # 6. Boolean subtraction
        subtracted_mass = apply_subtractions(original_mass, config)

        # 7. Building core placement (optional)
        if p.core_generation_enabled:
            cores = find_building_cores(subtracted_mass, column_grid, p.max_face_distance)
            subtracted_mass.cores = cores
            for floor in subtracted_mass.floors:
                floor.cores = cores

        return original_mass, subtracted_mass, config
