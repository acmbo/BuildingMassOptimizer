"""
Unit tests for BuildingGrid.

Run from project root:
    pytest test/Models/test_building_grid.py -v
"""
import sys
import os
import math
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from models import BuildingMass, BuildingGrid, CellMode, GridCell


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

# A simple 10 × 6 rectangle, 3 floors of height 3.0  →  AABB 10 × 6 × 9
POLYGON = [(0, 0, 0), (10, 0, 0), (10, 6, 0), (0, 6, 0)]
FLOOR_HEIGHT = 3.0
NUM_FLOORS = 3

def make_mass() -> BuildingMass:
    return BuildingMass.create(POLYGON, FLOOR_HEIGHT, NUM_FLOORS)


# ---------------------------------------------------------------------------
# CellMode.FIXED_SIZE – green tests (expected to pass)
# ---------------------------------------------------------------------------

class TestFixedSizeMode(unittest.TestCase):

    def setUp(self):
        self.mass = make_mass()
        self.grid = BuildingGrid.create(self.mass, CellMode.FIXED_SIZE, cell_size=2.0)

    def test_cell_mode_stored(self):
        self.assertEqual(self.grid.cell_mode, CellMode.FIXED_SIZE)

    def test_cell_size_stored(self):
        self.assertAlmostEqual(self.grid.cell_size, 2.0)

    def test_nx(self):
        # OCC brepbndlib pads the AABB slightly, so derive expected from actual AABB
        xmin, _, _ = self.grid.aabb_min
        xmax, _, _ = self.grid.aabb_max
        expected = math.ceil((xmax - xmin) / 2.0)
        self.assertEqual(self.grid.nx, expected)

    def test_ny(self):
        _, ymin, _ = self.grid.aabb_min
        _, ymax, _ = self.grid.aabb_max
        expected = math.ceil((ymax - ymin) / 2.0)
        self.assertEqual(self.grid.ny, expected)

    def test_nz_equals_num_floors(self):
        self.assertEqual(self.grid.nz, NUM_FLOORS)

    def test_total_cells(self):
        self.assertEqual(self.grid.total_cells, self.grid.nx * self.grid.ny * self.grid.nz)

    def test_cell_list_length(self):
        self.assertEqual(len(self.grid.cells), self.grid.total_cells)

    def test_cell_size_x_tiles_aabb(self):
        # nx cells of cell_size_x should exactly cover width
        xmin, _, _ = self.grid.aabb_min
        xmax, _, _ = self.grid.aabb_max
        self.assertAlmostEqual(self.grid.nx * self.grid.cell_size_x, xmax - xmin)

    def test_cell_size_y_tiles_aabb(self):
        _, ymin, _ = self.grid.aabb_min
        _, ymax, _ = self.grid.aabb_max
        self.assertAlmostEqual(self.grid.ny * self.grid.cell_size_y, ymax - ymin)

    def test_cell_size_z_equals_floor_height(self):
        self.assertAlmostEqual(self.grid.cell_size_z, FLOOR_HEIGHT)

    def test_aabb_zmin_is_zero(self):
        self.assertAlmostEqual(self.grid.aabb_min[2], 0.0, places=3)

    def test_aabb_zmax_equals_total_height(self):
        self.assertAlmostEqual(self.grid.aabb_max[2], self.mass.total_height, places=3)


# ---------------------------------------------------------------------------
# CellMode.CELL_COUNT – green tests
# ---------------------------------------------------------------------------

class TestCellCountMode(unittest.TestCase):

    def setUp(self):
        self.mass = make_mass()
        # longest axis = X (width=10); 5 cells → cell_size = 10/5 = 2.0
        self.grid = BuildingGrid.create(self.mass, CellMode.CELL_COUNT, cell_count=5)

    def test_cell_mode_stored(self):
        self.assertEqual(self.grid.cell_mode, CellMode.CELL_COUNT)

    def test_cell_size_derived_from_longest_axis(self):
        # max(10, 6) / 5 = 2.0
        self.assertAlmostEqual(self.grid.cell_size, 2.0)

    def test_nx_along_longest_axis(self):
        self.assertEqual(self.grid.nx, 5)

    def test_ny_shorter_axis(self):
        _, ymin, _ = self.grid.aabb_min
        _, ymax, _ = self.grid.aabb_max
        expected = math.ceil((ymax - ymin) / self.grid.cell_size)
        self.assertEqual(self.grid.ny, expected)

    def test_total_cells(self):
        self.assertEqual(self.grid.total_cells, self.grid.nx * self.grid.ny * self.grid.nz)

    def test_cell_count_1_gives_one_column(self):
        grid = BuildingGrid.create(self.mass, CellMode.CELL_COUNT, cell_count=1)
        self.assertEqual(grid.nx, 1)
        self.assertEqual(grid.ny, 1)


# ---------------------------------------------------------------------------
# GridCell – green tests
# ---------------------------------------------------------------------------

class TestGridCell(unittest.TestCase):

    def setUp(self):
        self.mass = make_mass()
        self.grid = BuildingGrid.create(self.mass, CellMode.FIXED_SIZE, cell_size=2.0)

    def test_get_cell_returns_correct_indices(self):
        cell = self.grid.get_cell(1, 2, 0)
        self.assertEqual(cell.ix, 1)
        self.assertEqual(cell.iy, 2)
        self.assertEqual(cell.iz, 0)

    def test_cell_center_is_midpoint(self):
        cell = self.grid.get_cell(0, 0, 0)
        expected_cx = (cell.min_pt[0] + cell.max_pt[0]) / 2
        expected_cy = (cell.min_pt[1] + cell.max_pt[1]) / 2
        expected_cz = (cell.min_pt[2] + cell.max_pt[2]) / 2
        self.assertAlmostEqual(cell.center[0], expected_cx)
        self.assertAlmostEqual(cell.center[1], expected_cy)
        self.assertAlmostEqual(cell.center[2], expected_cz)

    def test_first_cell_min_pt_at_aabb_origin(self):
        cell = self.grid.get_cell(0, 0, 0)
        self.assertAlmostEqual(cell.min_pt[0], self.grid.aabb_min[0], places=5)
        self.assertAlmostEqual(cell.min_pt[1], self.grid.aabb_min[1], places=5)
        self.assertAlmostEqual(cell.min_pt[2], self.grid.aabb_min[2], places=5)

    def test_last_cell_max_pt_at_aabb_corner(self):
        cell = self.grid.get_cell(self.grid.nx - 1, self.grid.ny - 1, self.grid.nz - 1)
        self.assertAlmostEqual(cell.max_pt[0], self.grid.aabb_max[0], places=5)
        self.assertAlmostEqual(cell.max_pt[1], self.grid.aabb_max[1], places=5)
        self.assertAlmostEqual(cell.max_pt[2], self.grid.aabb_max[2], places=5)

    def test_cells_at_floor_count(self):
        floor_cells = self.grid.cells_at_floor(0)
        self.assertEqual(len(floor_cells), self.grid.nx * self.grid.ny)

    def test_cells_at_floor_all_same_iz(self):
        for cell in self.grid.cells_at_floor(1):
            self.assertEqual(cell.iz, 1)

    def test_adjacent_cells_share_face(self):
        # cell (0,0,0) and (1,0,0) must share the X face
        c0 = self.grid.get_cell(0, 0, 0)
        c1 = self.grid.get_cell(1, 0, 0)
        self.assertAlmostEqual(c0.max_pt[0], c1.min_pt[0], places=5)


# ---------------------------------------------------------------------------
# Validation – red tests (invalid input must raise ValueError)
# ---------------------------------------------------------------------------

class TestValidation(unittest.TestCase):

    def setUp(self):
        self.mass = make_mass()

    def test_fixed_size_missing_cell_size_raises(self):
        with self.assertRaises(ValueError):
            BuildingGrid.create(self.mass, CellMode.FIXED_SIZE)

    def test_fixed_size_zero_cell_size_raises(self):
        with self.assertRaises(ValueError):
            BuildingGrid.create(self.mass, CellMode.FIXED_SIZE, cell_size=0)

    def test_fixed_size_negative_cell_size_raises(self):
        with self.assertRaises(ValueError):
            BuildingGrid.create(self.mass, CellMode.FIXED_SIZE, cell_size=-1.0)

    def test_cell_count_missing_count_raises(self):
        with self.assertRaises(ValueError):
            BuildingGrid.create(self.mass, CellMode.CELL_COUNT)

    def test_cell_count_zero_raises(self):
        with self.assertRaises(ValueError):
            BuildingGrid.create(self.mass, CellMode.CELL_COUNT, cell_count=0)

    def test_cell_count_negative_raises(self):
        with self.assertRaises(ValueError):
            BuildingGrid.create(self.mass, CellMode.CELL_COUNT, cell_count=-5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
