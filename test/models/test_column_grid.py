"""
Unit tests for ColumnGrid.

Run from project root:
    conda run -n pyoccEnv python -m pytest test/models/test_column_grid.py -v
"""
import sys
import os
import math
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from models import BuildingMass, SpanMode, ColumnGrid, Subtractor, SubtractorType


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

# Simple axis-aligned rectangle: 10 wide × 8 deep, origin at (0, 0)
RECT_POLYGON = [(0, 0, 0), (10, 0, 0), (10, 8, 0), (0, 8, 0)]

# Offset rectangle: same size but starting at (2, 3)
OFFSET_POLYGON = [(2, 3, 0), (12, 3, 0), (12, 11, 0), (2, 11, 0)]

# 5-sided irregular polygon (same as used in test_buildinggrid.py)
IRREGULAR_POLYGON = [(0, 0, 0), (10, 0, 0), (10, 6, 0), (4, 10, 0), (0, 10, 0)]

FLOOR_HEIGHT = 3.0
NUM_FLOORS = 5


def make_rect_mass() -> BuildingMass:
    return BuildingMass.create(RECT_POLYGON, FLOOR_HEIGHT, NUM_FLOORS)


def make_offset_mass() -> BuildingMass:
    return BuildingMass.create(OFFSET_POLYGON, FLOOR_HEIGHT, NUM_FLOORS)


def make_irregular_mass() -> BuildingMass:
    return BuildingMass.create(IRREGULAR_POLYGON, FLOOR_HEIGHT, NUM_FLOORS)


def make_subtractor(x=1.5, y=1.5, width=3.0, depth=3.0) -> Subtractor:
    return Subtractor(
        x=x, y=y, width=width, depth=depth,
        z_bottom=0.0, z_top=9.0,
        subtractor_type=SubtractorType.VERTICAL,
    )


# ---------------------------------------------------------------------------
# SpanMode.FIXED_SPAN – green tests
# ---------------------------------------------------------------------------

class TestFixedSpanMode(unittest.TestCase):

    def setUp(self):
        self.mass = make_rect_mass()
        # bbox = 10 × 8; span 4 → nx=ceil(10/4)=3, ny=ceil(8/4)=2
        self.grid = ColumnGrid.create(self.mass, SpanMode.FIXED_SPAN, span_x=4.0, span_y=4.0)

    def test_span_mode_stored(self):
        self.assertEqual(self.grid.span_mode, SpanMode.FIXED_SPAN)

    def test_span_x_stored(self):
        self.assertAlmostEqual(self.grid.span_x, 4.0)

    def test_span_y_stored(self):
        self.assertAlmostEqual(self.grid.span_y, 4.0)

    def test_nx_spans_derived_with_ceil(self):
        # ceil(10 / 4) = 3
        self.assertEqual(self.grid.nx_spans, 3)

    def test_ny_spans_derived_with_ceil(self):
        # ceil(8 / 4) = 2
        self.assertEqual(self.grid.ny_spans, 2)

    def test_grid_lines_x_count(self):
        self.assertEqual(len(self.grid.grid_lines_x), self.grid.nx_spans + 1)

    def test_grid_lines_y_count(self):
        self.assertEqual(len(self.grid.grid_lines_y), self.grid.ny_spans + 1)

    def test_total_width_covers_bbox(self):
        bbox_width = max(p[0] for p in RECT_POLYGON) - min(p[0] for p in RECT_POLYGON)
        self.assertGreaterEqual(self.grid.total_width, bbox_width - 1e-9)

    def test_total_depth_covers_bbox(self):
        bbox_depth = max(p[1] for p in RECT_POLYGON) - min(p[1] for p in RECT_POLYGON)
        self.assertGreaterEqual(self.grid.total_depth, bbox_depth - 1e-9)

    def test_total_width_formula(self):
        self.assertAlmostEqual(self.grid.total_width, self.grid.nx_spans * self.grid.span_x)

    def test_total_depth_formula(self):
        self.assertAlmostEqual(self.grid.total_depth, self.grid.ny_spans * self.grid.span_y)

    def test_snap_positions_x_count(self):
        self.assertEqual(len(self.grid.snap_positions_x), self.grid.nx_spans * 4 + 1)

    def test_snap_positions_y_count(self):
        self.assertEqual(len(self.grid.snap_positions_y), self.grid.ny_spans * 4 + 1)


# ---------------------------------------------------------------------------
# SpanMode.SPAN_COUNT – green tests
# ---------------------------------------------------------------------------

class TestSpanCountMode(unittest.TestCase):

    def setUp(self):
        self.mass = make_rect_mass()
        # bbox = 10 × 8; 2 spans each → span_x = 5.0, span_y = 4.0
        self.grid = ColumnGrid.create(self.mass, SpanMode.SPAN_COUNT, nx_spans=2, ny_spans=2)

    def test_span_mode_stored(self):
        self.assertEqual(self.grid.span_mode, SpanMode.SPAN_COUNT)

    def test_nx_spans_stored(self):
        self.assertEqual(self.grid.nx_spans, 2)

    def test_ny_spans_stored(self):
        self.assertEqual(self.grid.ny_spans, 2)

    def test_span_x_derived(self):
        # 10 / 2 = 5.0
        self.assertAlmostEqual(self.grid.span_x, 5.0)

    def test_span_y_derived(self):
        # 8 / 2 = 4.0
        self.assertAlmostEqual(self.grid.span_y, 4.0)

    def test_grid_lines_x_count(self):
        self.assertEqual(len(self.grid.grid_lines_x), 3)

    def test_grid_lines_y_count(self):
        self.assertEqual(len(self.grid.grid_lines_y), 3)

    def test_total_width_equals_bbox(self):
        bbox_width = max(p[0] for p in RECT_POLYGON) - min(p[0] for p in RECT_POLYGON)
        self.assertAlmostEqual(self.grid.total_width, bbox_width)

    def test_total_depth_equals_bbox(self):
        bbox_depth = max(p[1] for p in RECT_POLYGON) - min(p[1] for p in RECT_POLYGON)
        self.assertAlmostEqual(self.grid.total_depth, bbox_depth)


# ---------------------------------------------------------------------------
# Grid line geometry – green tests
# ---------------------------------------------------------------------------

class TestGridLineGeometry(unittest.TestCase):

    def setUp(self):
        self.mass = make_rect_mass()
        self.grid = ColumnGrid.create(self.mass, SpanMode.FIXED_SPAN, span_x=4.0, span_y=4.0)

    def test_origin_at_polygon_xmin(self):
        poly_xmin = min(p[0] for p in RECT_POLYGON)
        self.assertAlmostEqual(self.grid.origin_x, poly_xmin)

    def test_origin_at_polygon_ymin(self):
        poly_ymin = min(p[1] for p in RECT_POLYGON)
        self.assertAlmostEqual(self.grid.origin_y, poly_ymin)

    def test_first_grid_line_x_at_origin(self):
        self.assertAlmostEqual(self.grid.grid_lines_x[0], self.grid.origin_x)

    def test_first_grid_line_y_at_origin(self):
        self.assertAlmostEqual(self.grid.grid_lines_y[0], self.grid.origin_y)

    def test_grid_lines_x_uniform_spacing(self):
        for i in range(len(self.grid.grid_lines_x) - 1):
            gap = self.grid.grid_lines_x[i + 1] - self.grid.grid_lines_x[i]
            self.assertAlmostEqual(gap, self.grid.span_x)

    def test_grid_lines_y_uniform_spacing(self):
        for j in range(len(self.grid.grid_lines_y) - 1):
            gap = self.grid.grid_lines_y[j + 1] - self.grid.grid_lines_y[j]
            self.assertAlmostEqual(gap, self.grid.span_y)

    def test_last_grid_line_x_at_or_beyond_bbox(self):
        poly_xmax = max(p[0] for p in RECT_POLYGON)
        self.assertGreaterEqual(self.grid.grid_lines_x[-1], poly_xmax - 1e-9)

    def test_last_grid_line_y_at_or_beyond_bbox(self):
        poly_ymax = max(p[1] for p in RECT_POLYGON)
        self.assertGreaterEqual(self.grid.grid_lines_y[-1], poly_ymax - 1e-9)


# ---------------------------------------------------------------------------
# Offset polygon – origin is polygon bbox, not always (0, 0)
# ---------------------------------------------------------------------------

class TestOffsetPolygon(unittest.TestCase):

    def setUp(self):
        self.mass = make_offset_mass()
        self.grid = ColumnGrid.create(self.mass, SpanMode.FIXED_SPAN, span_x=4.0, span_y=4.0)

    def test_origin_x_is_polygon_xmin(self):
        poly_xmin = min(p[0] for p in OFFSET_POLYGON)  # 2.0
        self.assertAlmostEqual(self.grid.origin_x, poly_xmin)

    def test_origin_y_is_polygon_ymin(self):
        poly_ymin = min(p[1] for p in OFFSET_POLYGON)  # 3.0
        self.assertAlmostEqual(self.grid.origin_y, poly_ymin)

    def test_first_grid_line_x_matches_origin(self):
        self.assertAlmostEqual(self.grid.grid_lines_x[0], 2.0)

    def test_first_grid_line_y_matches_origin(self):
        self.assertAlmostEqual(self.grid.grid_lines_y[0], 3.0)

    def test_origin_not_zero(self):
        # Confirm the grid is not hardcoded to start at 0
        self.assertNotAlmostEqual(self.grid.origin_x, 0.0)
        self.assertNotAlmostEqual(self.grid.origin_y, 0.0)


# ---------------------------------------------------------------------------
# Irregular polygon – grid still fits bbox
# ---------------------------------------------------------------------------

class TestIrregularPolygon(unittest.TestCase):

    def setUp(self):
        # IRREGULAR_POLYGON bbox: x in [0, 10], y in [0, 10]
        self.mass = make_irregular_mass()
        self.grid = ColumnGrid.create(self.mass, SpanMode.SPAN_COUNT, nx_spans=2, ny_spans=2)

    def test_origin_from_polygon_not_occ_aabb(self):
        poly_xmin = min(p[0] for p in IRREGULAR_POLYGON)
        self.assertAlmostEqual(self.grid.origin_x, poly_xmin)

    def test_grid_covers_full_polygon_bbox(self):
        poly_xmax = max(p[0] for p in IRREGULAR_POLYGON)
        poly_ymax = max(p[1] for p in IRREGULAR_POLYGON)
        self.assertGreaterEqual(self.grid.grid_lines_x[-1], poly_xmax - 1e-9)
        self.assertGreaterEqual(self.grid.grid_lines_y[-1], poly_ymax - 1e-9)

    def test_span_derived_from_irregular_bbox(self):
        # bbox 10 × 10, 2 spans → 5.0 × 5.0
        self.assertAlmostEqual(self.grid.span_x, 5.0)
        self.assertAlmostEqual(self.grid.span_y, 5.0)


# ---------------------------------------------------------------------------
# Snap operations – green tests
# ---------------------------------------------------------------------------

class TestSnapToGrid(unittest.TestCase):

    def setUp(self):
        mass = make_rect_mass()
        # origin=(0,0), span=4, quarter positions at 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12
        self.grid = ColumnGrid.create(mass, SpanMode.FIXED_SPAN, span_x=4.0, span_y=4.0)

    def test_snap_x_exact_position(self):
        self.assertAlmostEqual(self.grid.snap_to_grid(4.0, "x"), 4.0)

    def test_snap_y_exact_position(self):
        self.assertAlmostEqual(self.grid.snap_to_grid(4.0, "y"), 4.0)

    def test_snap_x_rounds_to_nearest(self):
        # 1.9 is closer to 2.0 than to 1.0
        self.assertAlmostEqual(self.grid.snap_to_grid(1.9, "x"), 2.0)

    def test_snap_x_rounds_down(self):
        # 1.1 is closer to 1.0 than to 2.0
        self.assertAlmostEqual(self.grid.snap_to_grid(1.1, "x"), 1.0)

    def test_snap_result_is_on_snap_positions_x(self):
        result = self.grid.snap_to_grid(5.3, "x")
        self.assertTrue(any(abs(result - p) < 1e-9 for p in self.grid.snap_positions_x))

    def test_snap_result_is_on_snap_positions_y(self):
        result = self.grid.snap_to_grid(3.7, "y")
        self.assertTrue(any(abs(result - p) < 1e-9 for p in self.grid.snap_positions_y))

    def test_snap_x_value_before_origin_snaps_to_origin(self):
        # -0.3 is closer to 0.0 than to 1.0
        self.assertAlmostEqual(self.grid.snap_to_grid(-0.3, "x"), 0.0)

    def test_snap_x_value_beyond_grid_snaps_to_last(self):
        # 12.6 with nx_spans=3, span=4 → last snap at 12.0; 12.6 closer to 12.0
        self.assertAlmostEqual(self.grid.snap_to_grid(12.6, "x"), 12.0)


# ---------------------------------------------------------------------------
# align_subtractor – green tests
# ---------------------------------------------------------------------------

class TestAlignSubtractor(unittest.TestCase):

    def setUp(self):
        mass = make_rect_mass()
        # origin=(0,0), span=4.0 → quarter positions at 0, 1, 2, 3, 4, ...
        self.grid = ColumnGrid.create(mass, SpanMode.FIXED_SPAN, span_x=4.0, span_y=4.0)

    def test_aligned_x_on_snap_position(self):
        sub = make_subtractor(x=1.4, y=1.0, width=3.0, depth=3.0)
        result = self.grid.align_subtractor(sub)
        self.assertIsNotNone(result)
        self.assertTrue(any(abs(result.x - p) < 1e-9 for p in self.grid.snap_positions_x))

    def test_aligned_x_far_on_snap_position(self):
        sub = make_subtractor(x=1.4, y=1.0, width=3.0, depth=3.0)
        result = self.grid.align_subtractor(sub)
        self.assertIsNotNone(result)
        x_far = result.x + result.width
        self.assertTrue(any(abs(x_far - p) < 1e-9 for p in self.grid.snap_positions_x))

    def test_aligned_y_on_snap_position(self):
        sub = make_subtractor(x=1.0, y=1.4, width=3.0, depth=3.0)
        result = self.grid.align_subtractor(sub)
        self.assertIsNotNone(result)
        self.assertTrue(any(abs(result.y - p) < 1e-9 for p in self.grid.snap_positions_y))

    def test_aligned_y_far_on_snap_position(self):
        sub = make_subtractor(x=1.0, y=1.4, width=3.0, depth=3.0)
        result = self.grid.align_subtractor(sub)
        self.assertIsNotNone(result)
        y_far = result.y + result.depth
        self.assertTrue(any(abs(y_far - p) < 1e-9 for p in self.grid.snap_positions_y))

    def test_z_range_preserved(self):
        sub = make_subtractor()
        result = self.grid.align_subtractor(sub)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.z_bottom, sub.z_bottom)
        self.assertAlmostEqual(result.z_top, sub.z_top)

    def test_subtractor_type_preserved(self):
        sub = make_subtractor()
        result = self.grid.align_subtractor(sub)
        self.assertIsNotNone(result)
        self.assertEqual(result.subtractor_type, sub.subtractor_type)

    def test_already_aligned_subtractor_unchanged(self):
        # x=0, width=4 already on grid positions
        sub = make_subtractor(x=0.0, y=0.0, width=4.0, depth=4.0)
        result = self.grid.align_subtractor(sub)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.x, 0.0)
        self.assertAlmostEqual(result.width, 4.0)
        self.assertAlmostEqual(result.y, 0.0)
        self.assertAlmostEqual(result.depth, 4.0)

    def test_floor_independent_z_ignored(self):
        # Same subtractor, different Z ranges — snapped XY must be identical
        sub_low = Subtractor(x=1.5, y=1.5, width=3.0, depth=3.0,
                             z_bottom=0.0, z_top=3.0,
                             subtractor_type=SubtractorType.VERTICAL)
        sub_high = Subtractor(x=1.5, y=1.5, width=3.0, depth=3.0,
                              z_bottom=6.0, z_top=12.0,
                              subtractor_type=SubtractorType.VERTICAL)
        r_low = self.grid.align_subtractor(sub_low)
        r_high = self.grid.align_subtractor(sub_high)
        self.assertIsNotNone(r_low)
        self.assertIsNotNone(r_high)
        self.assertAlmostEqual(r_low.x, r_high.x)
        self.assertAlmostEqual(r_low.y, r_high.y)
        self.assertAlmostEqual(r_low.width, r_high.width)
        self.assertAlmostEqual(r_low.depth, r_high.depth)


# ---------------------------------------------------------------------------
# align_subtractor – deactivation (returns None)
# ---------------------------------------------------------------------------

class TestAlignSubtractorDeactivation(unittest.TestCase):

    def setUp(self):
        mass = make_rect_mass()
        # span=4, quarter positions at 0, 1, 2, 3, 4, ...
        self.grid = ColumnGrid.create(mass, SpanMode.FIXED_SPAN, span_x=4.0, span_y=4.0)

    def test_tiny_width_snaps_to_same_position_returns_none(self):
        # x=1.99, width=0.02 → both faces snap to 2.0 → width = 0 → deactivated
        sub = Subtractor(x=1.99, y=1.0, width=0.02, depth=3.0,
                         z_bottom=0.0, z_top=9.0,
                         subtractor_type=SubtractorType.VERTICAL)
        result = self.grid.align_subtractor(sub)
        self.assertIsNone(result)

    def test_tiny_depth_snaps_to_same_position_returns_none(self):
        sub = Subtractor(x=1.0, y=1.99, width=3.0, depth=0.02,
                         z_bottom=0.0, z_top=9.0,
                         subtractor_type=SubtractorType.VERTICAL)
        result = self.grid.align_subtractor(sub)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Floor-independence – green tests
# ---------------------------------------------------------------------------

class TestFloorIndependence(unittest.TestCase):

    def test_grid_has_no_floors_attribute(self):
        mass = make_rect_mass()
        grid = ColumnGrid.create(mass, SpanMode.FIXED_SPAN, span_x=4.0, span_y=4.0)
        self.assertFalse(hasattr(grid, "floors"))

    def test_grid_has_no_nz_attribute(self):
        mass = make_rect_mass()
        grid = ColumnGrid.create(mass, SpanMode.FIXED_SPAN, span_x=4.0, span_y=4.0)
        self.assertFalse(hasattr(grid, "nz"))

    def test_align_subtractor_same_result_regardless_of_floor(self):
        mass = BuildingMass.create(RECT_POLYGON, FLOOR_HEIGHT, 8)
        grid = ColumnGrid.create(mass, SpanMode.FIXED_SPAN, span_x=4.0, span_y=4.0)
        results = []
        for floor in mass.floors:
            # Build a subtractor at this floor's elevation, same XY each time
            sub = Subtractor(x=1.5, y=1.5, width=3.0, depth=3.0,
                             z_bottom=floor.elevation,
                             z_top=floor.elevation + floor.floor_height,
                             subtractor_type=SubtractorType.VERTICAL)
            results.append(grid.align_subtractor(sub))
        # All results must have identical snapped XY
        for r in results[1:]:
            self.assertAlmostEqual(r.x, results[0].x)
            self.assertAlmostEqual(r.y, results[0].y)
            self.assertAlmostEqual(r.width, results[0].width)
            self.assertAlmostEqual(r.depth, results[0].depth)


# ---------------------------------------------------------------------------
# Validation – red tests (invalid input must raise ValueError)
# ---------------------------------------------------------------------------

class TestValidation(unittest.TestCase):

    def setUp(self):
        self.mass = make_rect_mass()

    def test_fixed_span_zero_span_x_raises(self):
        with self.assertRaises(ValueError):
            ColumnGrid.create(self.mass, SpanMode.FIXED_SPAN, span_x=0.0, span_y=4.0)

    def test_fixed_span_negative_span_x_raises(self):
        with self.assertRaises(ValueError):
            ColumnGrid.create(self.mass, SpanMode.FIXED_SPAN, span_x=-1.0, span_y=4.0)

    def test_fixed_span_missing_span_x_raises(self):
        with self.assertRaises(ValueError):
            ColumnGrid.create(self.mass, SpanMode.FIXED_SPAN, span_y=4.0)

    def test_fixed_span_zero_span_y_raises(self):
        with self.assertRaises(ValueError):
            ColumnGrid.create(self.mass, SpanMode.FIXED_SPAN, span_x=4.0, span_y=0.0)

    def test_fixed_span_negative_span_y_raises(self):
        with self.assertRaises(ValueError):
            ColumnGrid.create(self.mass, SpanMode.FIXED_SPAN, span_x=4.0, span_y=-2.0)

    def test_fixed_span_missing_span_y_raises(self):
        with self.assertRaises(ValueError):
            ColumnGrid.create(self.mass, SpanMode.FIXED_SPAN, span_x=4.0)

    def test_span_count_zero_nx_raises(self):
        with self.assertRaises(ValueError):
            ColumnGrid.create(self.mass, SpanMode.SPAN_COUNT, nx_spans=0, ny_spans=2)

    def test_span_count_negative_nx_raises(self):
        with self.assertRaises(ValueError):
            ColumnGrid.create(self.mass, SpanMode.SPAN_COUNT, nx_spans=-1, ny_spans=2)

    def test_span_count_missing_nx_raises(self):
        with self.assertRaises(ValueError):
            ColumnGrid.create(self.mass, SpanMode.SPAN_COUNT, ny_spans=2)

    def test_span_count_zero_ny_raises(self):
        with self.assertRaises(ValueError):
            ColumnGrid.create(self.mass, SpanMode.SPAN_COUNT, nx_spans=2, ny_spans=0)

    def test_snap_invalid_axis_raises(self):
        mass = make_rect_mass()
        grid = ColumnGrid.create(mass, SpanMode.FIXED_SPAN, span_x=4.0, span_y=4.0)
        with self.assertRaises(ValueError):
            grid.snap_to_grid(5.0, "z")


if __name__ == "__main__":
    unittest.main(verbosity=2)
