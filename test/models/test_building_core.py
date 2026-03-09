"""
Unit tests for BuildingCore and find_building_cores.

Run from project root:
    conda run -n pyoccEnv python -m pytest test/models/test_building_core.py -v
"""
import sys
import os
import math
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from models import (
    BuildingMass,
    SpanMode,
    ColumnGrid,
    Subtractor,
    SubtractorType,
    SubtractionConfig,
    BuildingCore,
    find_building_cores,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

# 20 × 20 m square — small enough that one centroid core covers everything
# at 35 m (all face midpoints are ≤ ~14 m from center)
SMALL_POLYGON = [(0, 0, 0), (20, 0, 0), (20, 20, 0), (0, 20, 0)]

# 80 × 20 m rectangle — long axis should force a second core
LONG_POLYGON = [(0, 0, 0), (80, 0, 0), (80, 20, 0), (0, 20, 0)]

FLOOR_HEIGHT = 3.5
NUM_FLOORS = 6


def make_mass(polygon=SMALL_POLYGON) -> BuildingMass:
    return BuildingMass.create(polygon, FLOOR_HEIGHT, NUM_FLOORS)


def make_grid(mass: BuildingMass, span: float = 4.0) -> ColumnGrid:
    return ColumnGrid.create(mass, SpanMode.FIXED_SPAN, span_x=span, span_y=span)


# ---------------------------------------------------------------------------
# BuildingCore dataclass — green tests
# ---------------------------------------------------------------------------

class TestBuildingCoreFields(unittest.TestCase):

    def setUp(self):
        self.core = BuildingCore(
            center_x=10.0, center_y=8.0,
            width=4.0, depth=4.0,
            column_ix=2, column_iy=1,
        )

    def test_center_x_stored(self):
        self.assertAlmostEqual(self.core.center_x, 10.0)

    def test_center_y_stored(self):
        self.assertAlmostEqual(self.core.center_y, 8.0)

    def test_width_stored(self):
        self.assertAlmostEqual(self.core.width, 4.0)

    def test_depth_stored(self):
        self.assertAlmostEqual(self.core.depth, 4.0)

    def test_column_ix_stored(self):
        self.assertEqual(self.core.column_ix, 2)

    def test_column_iy_stored(self):
        self.assertEqual(self.core.column_iy, 1)

    def test_x_min(self):
        self.assertAlmostEqual(self.core.x_min, 8.0)

    def test_x_max(self):
        self.assertAlmostEqual(self.core.x_max, 12.0)

    def test_y_min(self):
        self.assertAlmostEqual(self.core.y_min, 6.0)

    def test_y_max(self):
        self.assertAlmostEqual(self.core.y_max, 10.0)

    def test_x_min_x_max_width_consistent(self):
        self.assertAlmostEqual(self.core.x_max - self.core.x_min, self.core.width)

    def test_y_min_y_max_depth_consistent(self):
        self.assertAlmostEqual(self.core.y_max - self.core.y_min, self.core.depth)


# ---------------------------------------------------------------------------
# BuildingCore validation — red tests
# ---------------------------------------------------------------------------

class TestBuildingCoreValidation(unittest.TestCase):

    def _make(self, **kwargs):
        defaults = dict(center_x=5.0, center_y=5.0, width=4.0, depth=4.0,
                        column_ix=0, column_iy=0)
        defaults.update(kwargs)
        return BuildingCore(**defaults)

    def test_zero_width_raises(self):
        with self.assertRaises(ValueError):
            self._make(width=0.0)

    def test_negative_width_raises(self):
        with self.assertRaises(ValueError):
            self._make(width=-1.0)

    def test_zero_depth_raises(self):
        with self.assertRaises(ValueError):
            self._make(depth=0.0)

    def test_negative_depth_raises(self):
        with self.assertRaises(ValueError):
            self._make(depth=-2.0)

    def test_negative_column_ix_raises(self):
        with self.assertRaises(ValueError):
            self._make(column_ix=-1)

    def test_negative_column_iy_raises(self):
        with self.assertRaises(ValueError):
            self._make(column_iy=-1)


# ---------------------------------------------------------------------------
# find_building_cores — green tests
# ---------------------------------------------------------------------------

class TestFindBuildingCoresSmall(unittest.TestCase):
    """20 × 20 m building — centroid (10, 10) covers all faces at 35 m."""

    def setUp(self):
        mass = make_mass(SMALL_POLYGON)
        grid = make_grid(mass, span=4.0)
        self.cores = find_building_cores(mass, grid, max_face_distance=35.0)
        self.grid = grid

    def test_returns_at_least_one_core(self):
        self.assertGreaterEqual(len(self.cores), 1)

    def test_single_core_covers_small_building(self):
        # 20 × 20 m: max face-midpoint distance from center ≈ 10√2 ≈ 14.1 m < 35 m
        self.assertEqual(len(self.cores), 1)

    def test_core_is_building_core_instance(self):
        for c in self.cores:
            self.assertIsInstance(c, BuildingCore)

    def test_core_center_on_column_grid_cell_center(self):
        # Cell centers at 2, 6, 10, 14, 18 for span=4 on [0, 20]
        for c in self.cores:
            cx = self.grid.grid_lines_x[c.column_ix] + self.grid.span_x / 2
            cy = self.grid.grid_lines_y[c.column_iy] + self.grid.span_y / 2
            self.assertAlmostEqual(c.center_x, cx, places=6)
            self.assertAlmostEqual(c.center_y, cy, places=6)

    def test_core_width_equals_span_x(self):
        for c in self.cores:
            self.assertAlmostEqual(c.width, self.grid.span_x)

    def test_core_depth_equals_span_y(self):
        for c in self.cores:
            self.assertAlmostEqual(c.depth, self.grid.span_y)

    def test_column_ix_valid_range(self):
        for c in self.cores:
            self.assertGreaterEqual(c.column_ix, 0)
            self.assertLess(c.column_ix, self.grid.nx_spans)

    def test_column_iy_valid_range(self):
        for c in self.cores:
            self.assertGreaterEqual(c.column_iy, 0)
            self.assertLess(c.column_iy, self.grid.ny_spans)


class TestFindBuildingCoresLong(unittest.TestCase):
    """80 × 20 m building — single centroid core at (40, 10) leaves the
    face midpoints near x=0 and x=80 uncovered at 35 m."""

    def setUp(self):
        mass = make_mass(LONG_POLYGON)
        grid = make_grid(mass, span=4.0)
        self.cores = find_building_cores(mass, grid, max_face_distance=35.0)
        self.mass = mass
        self.grid = grid

    def test_multiple_cores_for_long_building(self):
        self.assertGreaterEqual(len(self.cores), 2)

    def test_all_faces_covered(self):
        from models.building_core_engine import _extract_face_midpoints, _is_covered
        midpoints = _extract_face_midpoints(self.mass.floors[0].polygon_wire)
        for f in midpoints:
            self.assertTrue(
                _is_covered(f, self.cores, 35.0),
                msg=f"Face midpoint ({f.x:.1f}, {f.y:.1f}) is not covered",
            )


class TestFindBuildingCoresTightDistance(unittest.TestCase):
    """Very small max_face_distance forces many cores."""

    def test_small_distance_triggers_more_cores(self):
        mass = make_mass(SMALL_POLYGON)
        grid = make_grid(mass, span=4.0)
        # 5 m max distance on a 20 × 20 building — needs more than 1 core
        cores_tight = find_building_cores(mass, grid, max_face_distance=5.0)
        cores_loose = find_building_cores(mass, grid, max_face_distance=35.0)
        self.assertGreater(len(cores_tight), len(cores_loose))


# ---------------------------------------------------------------------------
# FloorData and BuildingMass cores field — green tests
# ---------------------------------------------------------------------------

class TestCoresFieldDefaults(unittest.TestCase):

    def test_building_mass_cores_default_empty(self):
        mass = make_mass()
        self.assertEqual(mass.cores, [])

    def test_floor_data_cores_default_empty(self):
        mass = make_mass()
        for floor in mass.floors:
            self.assertEqual(floor.cores, [])

    def test_assign_cores_to_mass(self):
        mass = make_mass()
        grid = make_grid(mass)
        cores = find_building_cores(mass, grid)
        mass.cores = cores
        self.assertEqual(len(mass.cores), len(cores))

    def test_propagate_cores_to_floors(self):
        mass = make_mass()
        grid = make_grid(mass)
        cores = find_building_cores(mass, grid)
        mass.cores = cores
        for floor in mass.floors:
            floor.cores = cores
        for floor in mass.floors:
            self.assertEqual(len(floor.cores), len(cores))


# ---------------------------------------------------------------------------
# align_subtractor with cores — green tests
# ---------------------------------------------------------------------------

class TestAlignSubtractorWithCores(unittest.TestCase):

    def setUp(self):
        mass = make_mass(SMALL_POLYGON)
        self.grid = make_grid(mass, span=4.0)
        # Core centered at (10, 10): x_min=8, x_max=12, y_min=8, y_max=12
        self.core = BuildingCore(
            center_x=10.0, center_y=10.0,
            width=4.0, depth=4.0,
            column_ix=2, column_iy=2,
        )

    def _make_sub(self, x, y, w, d):
        return Subtractor(
            x=x, y=y, width=w, depth=d,
            z_bottom=0.0, z_top=10.5,
            subtractor_type=SubtractorType.VERTICAL,
        )

    def test_face_near_core_x_min_snaps(self):
        # Subtractor left face at x=8.3, core.x_min=8.0 — gap=0.3 < threshold=2.0
        sub = self._make_sub(x=8.3, y=2.0, w=4.0, d=4.0)
        result = self.grid.align_subtractor(sub, cores=[self.core])
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.x, 8.0, places=5)

    def test_face_far_from_all_cores_unchanged(self):
        # Subtractor far left at x=1.0, no core edge nearby
        sub = self._make_sub(x=1.0, y=1.0, w=2.0, d=2.0)
        result_no_cores = self.grid.align_subtractor(sub)
        result_with_cores = self.grid.align_subtractor(sub, cores=[self.core])
        # x face should be identical — no core edge is within threshold at x=1
        self.assertIsNotNone(result_with_cores)
        self.assertAlmostEqual(result_no_cores.x, result_with_cores.x, places=5)

    def test_z_range_preserved_with_cores(self):
        sub = self._make_sub(x=8.3, y=2.0, w=4.0, d=4.0)
        result = self.grid.align_subtractor(sub, cores=[self.core])
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.z_bottom, sub.z_bottom)
        self.assertAlmostEqual(result.z_top, sub.z_top)

    def test_no_cores_behaves_as_before(self):
        sub = self._make_sub(x=1.4, y=1.4, w=3.0, d=3.0)
        result_no_cores = self.grid.align_subtractor(sub)
        result_none = self.grid.align_subtractor(sub, cores=None)
        self.assertIsNotNone(result_no_cores)
        self.assertIsNotNone(result_none)
        self.assertAlmostEqual(result_no_cores.x, result_none.x)
        self.assertAlmostEqual(result_no_cores.y, result_none.y)


# ---------------------------------------------------------------------------
# Regression: core must not be placed inside a subtracted courtyard void
# ---------------------------------------------------------------------------

class TestCoreNotInsideCourtyard(unittest.TestCase):
    """
    50 × 50 m building with a large central courtyard (20 × 20 m).
    After subtraction the centroid of all edge midpoints (inner + outer ring)
    is biased toward the void center.  The fix must place the core on solid
    material, not inside the courtyard.
    """

    COURTYARD_POLYGON = [(0, 0, 0), (50, 0, 0), (50, 50, 0), (0, 50, 0)]
    # Courtyard occupies x=[15,35], y=[15,35]
    COURTYARD_X = 15.0
    COURTYARD_Y = 15.0
    COURTYARD_W = 20.0
    COURTYARD_D = 20.0

    def setUp(self):
        from models.subtraction_engine import apply_subtractions

        mass = BuildingMass.create(
            self.COURTYARD_POLYGON, floor_height=3.5, num_floors=6
        )
        total_h = 3.5 * 6
        courtyard = Subtractor(
            x=self.COURTYARD_X,
            y=self.COURTYARD_Y,
            width=self.COURTYARD_W,
            depth=self.COURTYARD_D,
            z_bottom=0.0,
            z_top=total_h,
            subtractor_type=SubtractorType.VERTICAL,
        )
        config = SubtractionConfig(
            vertical_subtractors=[courtyard],
            horizontal_subtractors=[],
            min_plan_size=1.0,
            max_plan_size=100.0,
        )
        self.subtracted_mass = apply_subtractions(mass, config)
        self.grid = ColumnGrid.create(
            mass, SpanMode.FIXED_SPAN, span_x=5.0, span_y=5.0
        )
        self.cores = find_building_cores(self.subtracted_mass, self.grid, max_face_distance=35.0)

    def test_at_least_one_core_placed(self):
        self.assertGreaterEqual(len(self.cores), 1)

    def test_no_core_center_inside_courtyard(self):
        """Core centers must not fall within the courtyard bounding box."""
        void_xmin = self.COURTYARD_X
        void_xmax = self.COURTYARD_X + self.COURTYARD_W
        void_ymin = self.COURTYARD_Y
        void_ymax = self.COURTYARD_Y + self.COURTYARD_D
        for c in self.cores:
            inside_x = void_xmin < c.center_x < void_xmax
            inside_y = void_ymin < c.center_y < void_ymax
            self.assertFalse(
                inside_x and inside_y,
                msg=(
                    f"Core at ({c.center_x}, {c.center_y}) is inside the courtyard "
                    f"[{void_xmin},{void_xmax}] × [{void_ymin},{void_ymax}]"
                ),
            )


# ---------------------------------------------------------------------------
# Regression: core must not be placed inside a void that only spans upper floors
# ---------------------------------------------------------------------------

class TestCoreNotInsideUpperFloorVoid(unittest.TestCase):
    """
    50 × 50 m building with a horizontal subtractor that cuts away the center
    only on floors 3-6 (z=7 to z=21).  The ground floor is untouched, so a
    naive implementation (checking ground floor only) would incorrectly place
    a core at (25, 25) — inside the upper void.  The fix must reject any XY
    position that intersects a void on any floor.
    """

    POLYGON = [(0, 0, 0), (50, 0, 0), (50, 50, 0), (0, 50, 0)]
    FLOOR_HEIGHT = 3.5
    NUM_FLOORS = 6
    # Void cuts the center of floors 3-6: z=[7, 21]
    VOID_X = 15.0
    VOID_Y = 15.0
    VOID_W = 20.0
    VOID_D = 20.0
    VOID_Z_BOT = 7.0    # top of floor 2
    VOID_Z_TOP = 21.0   # top of floor 6

    def setUp(self):
        from models.subtraction_engine import apply_subtractions

        mass = BuildingMass.create(self.POLYGON, self.FLOOR_HEIGHT, self.NUM_FLOORS)
        upper_void = Subtractor(
            x=self.VOID_X,
            y=self.VOID_Y,
            width=self.VOID_W,
            depth=self.VOID_D,
            z_bottom=self.VOID_Z_BOT,
            z_top=self.VOID_Z_TOP,
            subtractor_type=SubtractorType.HORIZONTAL,
        )
        config = SubtractionConfig(
            vertical_subtractors=[],
            horizontal_subtractors=[upper_void],
            min_plan_size=1.0,
            max_plan_size=100.0,
        )
        self.subtracted_mass = apply_subtractions(mass, config)
        self.grid = ColumnGrid.create(
            mass, SpanMode.FIXED_SPAN, span_x=5.0, span_y=5.0
        )
        self.cores = find_building_cores(
            self.subtracted_mass, self.grid, max_face_distance=35.0
        )

    def test_at_least_one_core_placed(self):
        self.assertGreaterEqual(len(self.cores), 1)

    def test_no_core_center_inside_upper_void(self):
        """No core XY center must fall inside the upper void footprint."""
        void_xmin = self.VOID_X
        void_xmax = self.VOID_X + self.VOID_W
        void_ymin = self.VOID_Y
        void_ymax = self.VOID_Y + self.VOID_D
        for c in self.cores:
            inside_x = void_xmin < c.center_x < void_xmax
            inside_y = void_ymin < c.center_y < void_ymax
            self.assertFalse(
                inside_x and inside_y,
                msg=(
                    f"Core at ({c.center_x:.2f}, {c.center_y:.2f}) is inside the upper-floor void "
                    f"[{void_xmin},{void_xmax}] × [{void_ymin},{void_ymax}]"
                ),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
