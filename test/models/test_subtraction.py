"""
Unit tests for the subtractive form generation feature.

Tests follow the red/green principle:
  - Green tests: verify correct behaviour (valid inputs, expected outputs).
  - Red tests:   verify that invalid inputs raise the correct errors (ValueError).

Run from project root:
    conda run -n pyoccEnv python -m pytest test/models/test_subtraction.py -v
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from models import BuildingMass
from models.subtractor import Subtractor, SubtractorType, SubtractionConfig
from models.subtraction_engine import (
    apply_subtractions,
    extract_bottom_wire,
    _validate_plan_size,
    _validate_vertical,
    _validate_horizontal,
)
from OCC.Core.BRepCheck import BRepCheck_Analyzer


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

POLYGON = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)]
FLOOR_HEIGHT = 3.0
NUM_FLOORS = 5


def make_mass() -> BuildingMass:
    return BuildingMass.create(POLYGON, FLOOR_HEIGHT, NUM_FLOORS)


def make_vertical(x=2.0, y=2.0, w=4.0, d=4.0, z_bot=0.0, z_top=15.0) -> Subtractor:
    return Subtractor(x, y, w, d, z_bot, z_top, SubtractorType.VERTICAL)


def make_horizontal(x=0.0, y=0.0, w=10.0, d=10.0, z_bot=0.0, z_top=3.0) -> Subtractor:
    return Subtractor(x, y, w, d, z_bot, z_top, SubtractorType.HORIZONTAL)


# ===========================================================================
# RED TESTS — invalid inputs must raise ValueError
# ===========================================================================

class TestSubtractorValidation(unittest.TestCase):
    """Subtractor dataclass validates geometry on creation."""

    def test_zero_width_raises(self):
        with self.assertRaises(ValueError):
            Subtractor(0, 0, 0.0, 4.0, 0.0, 3.0, SubtractorType.VERTICAL)

    def test_negative_width_raises(self):
        with self.assertRaises(ValueError):
            Subtractor(0, 0, -2.0, 4.0, 0.0, 3.0, SubtractorType.VERTICAL)

    def test_zero_depth_raises(self):
        with self.assertRaises(ValueError):
            Subtractor(0, 0, 4.0, 0.0, 0.0, 3.0, SubtractorType.VERTICAL)

    def test_negative_depth_raises(self):
        with self.assertRaises(ValueError):
            Subtractor(0, 0, 4.0, -1.0, 0.0, 3.0, SubtractorType.VERTICAL)

    def test_z_top_equals_z_bottom_raises(self):
        with self.assertRaises(ValueError):
            Subtractor(0, 0, 4.0, 4.0, 5.0, 5.0, SubtractorType.VERTICAL)

    def test_z_top_less_than_z_bottom_raises(self):
        with self.assertRaises(ValueError):
            Subtractor(0, 0, 4.0, 4.0, 6.0, 3.0, SubtractorType.VERTICAL)


class TestSubtractionConfigValidation(unittest.TestCase):
    """SubtractionConfig validates threshold values on creation."""

    def test_snap_threshold_above_1_raises(self):
        with self.assertRaises(ValueError):
            SubtractionConfig(vertical_snap_threshold=1.5)

    def test_snap_threshold_negative_raises(self):
        with self.assertRaises(ValueError):
            SubtractionConfig(vertical_snap_threshold=-0.1)

    def test_horizontal_ratio_zero_raises(self):
        with self.assertRaises(ValueError):
            SubtractionConfig(horizontal_max_height_ratio=0.0)

    def test_horizontal_ratio_above_1_raises(self):
        with self.assertRaises(ValueError):
            SubtractionConfig(horizontal_max_height_ratio=1.5)

    def test_negative_min_plan_size_raises(self):
        with self.assertRaises(ValueError):
            SubtractionConfig(min_plan_size=-1.0)

    def test_zero_max_plan_size_raises(self):
        with self.assertRaises(ValueError):
            SubtractionConfig(max_plan_size=0.0)

    def test_negative_max_plan_size_raises(self):
        with self.assertRaises(ValueError):
            SubtractionConfig(max_plan_size=-5.0)


# ===========================================================================
# GREEN TESTS — correct constraint behaviour (no OCC geometry needed)
# ===========================================================================

class TestPlanSizeConstraint(unittest.TestCase):
    """_validate_plan_size: clip oversized, deactivate undersized."""

    def _config(self, min_s=0.0, max_s=float("inf")):
        return SubtractionConfig(min_plan_size=min_s, max_plan_size=max_s)

    def test_within_limits_unchanged(self):
        s = make_vertical(w=4.0, d=4.0)
        result = _validate_plan_size(s, self._config(min_s=2.0, max_s=6.0))
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.width, 4.0)
        self.assertAlmostEqual(result.depth, 4.0)

    def test_width_clipped_to_max(self):
        s = make_vertical(w=8.0, d=4.0)
        result = _validate_plan_size(s, self._config(max_s=5.0))
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.width, 5.0)

    def test_depth_clipped_to_max(self):
        s = make_vertical(w=4.0, d=9.0)
        result = _validate_plan_size(s, self._config(max_s=5.0))
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.depth, 5.0)

    def test_both_dimensions_clipped(self):
        s = make_vertical(w=8.0, d=9.0)
        result = _validate_plan_size(s, self._config(max_s=5.0))
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.width, 5.0)
        self.assertAlmostEqual(result.depth, 5.0)

    def test_width_below_min_deactivates(self):
        s = make_vertical(w=1.0, d=4.0)
        result = _validate_plan_size(s, self._config(min_s=2.0))
        self.assertIsNone(result)

    def test_depth_below_min_deactivates(self):
        s = make_vertical(w=4.0, d=1.0)
        result = _validate_plan_size(s, self._config(min_s=2.0))
        self.assertIsNone(result)


class TestVerticalConstraint(unittest.TestCase):
    """_validate_vertical: snap faces and deactivate if no face qualifies."""

    TOTAL_HEIGHT = FLOOR_HEIGHT * NUM_FLOORS  # 15.0
    THRESHOLD = 0.30  # default; snap zone = 4.5

    def _config(self, threshold=0.30):
        return SubtractionConfig(vertical_snap_threshold=threshold)

    def test_top_face_snaps_to_total_height(self):
        # z_top = 13.0, gap_top = 2.0, threshold = 0.30 * 15 = 4.5 → snaps
        s = make_vertical(z_bot=0.0, z_top=13.0)
        result = _validate_vertical(s, self.TOTAL_HEIGHT, self._config())
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.z_top, self.TOTAL_HEIGHT)

    def test_bottom_face_snaps_to_zero(self):
        # z_bottom = 2.0, gap_bottom = 2.0 < 4.5 → snaps
        s = make_vertical(z_bot=2.0, z_top=15.0)
        result = _validate_vertical(s, self.TOTAL_HEIGHT, self._config())
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.z_bottom, 0.0)

    def test_both_faces_snap(self):
        s = make_vertical(z_bot=1.0, z_top=14.0)
        result = _validate_vertical(s, self.TOTAL_HEIGHT, self._config())
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.z_bottom, 0.0)
        self.assertAlmostEqual(result.z_top, self.TOTAL_HEIGHT)

    def test_neither_face_snaps_deactivates(self):
        # z_bottom = 6.0, gap_bottom = 6.0 >= 4.5 → no snap
        # z_top    = 9.0, gap_top   = 6.0 >= 4.5 → no snap
        s = make_vertical(z_bot=6.0, z_top=9.0)
        result = _validate_vertical(s, self.TOTAL_HEIGHT, self._config())
        self.assertIsNone(result)

    def test_only_top_snaps_is_active(self):
        # z_bottom = 8.0 → gap 8.0 ≥ 4.5 → no snap
        # z_top = 14.0   → gap 1.0 < 4.5  → snaps
        s = make_vertical(z_bot=8.0, z_top=14.0)
        result = _validate_vertical(s, self.TOTAL_HEIGHT, self._config())
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.z_top, self.TOTAL_HEIGHT)
        self.assertAlmostEqual(result.z_bottom, 8.0)  # unchanged


class TestHorizontalConstraint(unittest.TestCase):
    """_validate_horizontal: clip too-tall, deactivate too-short."""

    TOTAL_HEIGHT = FLOOR_HEIGHT * NUM_FLOORS  # 15.0

    def _config(self, ratio=0.30):
        return SubtractionConfig(horizontal_max_height_ratio=ratio)

    def test_valid_height_unchanged(self):
        # height = 3.0 = floor_height; max = 0.30 * 15 = 4.5 → within range
        s = make_horizontal(z_bot=0.0, z_top=3.0)
        result = _validate_horizontal(s, FLOOR_HEIGHT, self.TOTAL_HEIGHT, self._config())
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.z_top - result.z_bottom, 3.0)

    def test_too_tall_is_clipped(self):
        # height = 9.0 > 0.30 * 15 = 4.5 → clipped to 4.5
        s = make_horizontal(z_bot=0.0, z_top=9.0)
        result = _validate_horizontal(s, FLOOR_HEIGHT, self.TOTAL_HEIGHT, self._config())
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.z_top - result.z_bottom, 4.5)

    def test_clipped_preserves_z_bottom(self):
        s = make_horizontal(z_bot=3.0, z_top=12.0)
        result = _validate_horizontal(s, FLOOR_HEIGHT, self.TOTAL_HEIGHT, self._config())
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.z_bottom, 3.0)

    def test_too_short_deactivates(self):
        # height = 1.0 < floor_height = 3.0 → deactivated
        s = make_horizontal(z_bot=0.0, z_top=1.0)
        result = _validate_horizontal(s, FLOOR_HEIGHT, self.TOTAL_HEIGHT, self._config())
        self.assertIsNone(result)

    def test_exactly_floor_height_is_valid(self):
        s = make_horizontal(z_bot=0.0, z_top=FLOOR_HEIGHT)
        result = _validate_horizontal(s, FLOOR_HEIGHT, self.TOTAL_HEIGHT, self._config())
        self.assertIsNotNone(result)


# ===========================================================================
# GREEN TESTS — apply_subtractions geometry (requires OCC)
# ===========================================================================

class TestApplySubtractions(unittest.TestCase):
    """apply_subtractions returns a valid BuildingMass with modified floors."""

    def setUp(self):
        self.mass = make_mass()

    def test_returns_building_mass(self):
        config = SubtractionConfig(
            vertical_subtractors=[make_vertical()]
        )
        result = apply_subtractions(self.mass, config)
        self.assertIsInstance(result, BuildingMass)

    def test_same_number_of_floors(self):
        config = SubtractionConfig(
            vertical_subtractors=[make_vertical()]
        )
        result = apply_subtractions(self.mass, config)
        self.assertEqual(len(result.floors), self.mass.num_floors)

    def test_empty_config_floors_unchanged(self):
        """No subtractors → floors are identical solid objects."""
        config = SubtractionConfig()
        result = apply_subtractions(self.mass, config)
        for orig, new in zip(self.mass.floors, result.floors):
            # Same solid (no cut applied)
            self.assertEqual(orig.solid, new.solid)

    def test_vertical_subtractor_modifies_all_floors(self):
        """A full-height vertical subtractor should modify every floor solid."""
        config = SubtractionConfig(
            vertical_subtractors=[make_vertical(z_bot=0.0, z_top=15.0)]
        )
        result = apply_subtractions(self.mass, config)
        for orig, new in zip(self.mass.floors, result.floors):
            self.assertIsNot(orig.solid, new.solid,
                             msg=f"Floor {orig.index} solid was not replaced")

    def test_vertical_subtractor_cut_solids_are_valid(self):
        """Cut solids must pass BRepCheck_Analyzer."""
        config = SubtractionConfig(
            vertical_subtractors=[make_vertical()]
        )
        result = apply_subtractions(self.mass, config)
        for floor in result.floors:
            analyzer = BRepCheck_Analyzer(floor.solid)
            self.assertTrue(analyzer.IsValid(),
                            msg=f"Floor {floor.index} solid failed validity check")

    def test_horizontal_subtractor_affects_only_overlapping_floor(self):
        """A one-floor-tall horizontal subtractor spanning only floor 0 (z=0..3)
        should modify floor 0 but not floor 1."""
        sub = make_horizontal(z_bot=0.0, z_top=3.0)
        config = SubtractionConfig(horizontal_subtractors=[sub])
        result = apply_subtractions(self.mass, config)
        # Floor 0 should be different (cut applied)
        self.assertIsNot(self.mass.floors[0].solid, result.floors[0].solid)
        # Floor 1 (elevation 3.0..6.0) — subtractor z_top == floor elevation start
        # so it does NOT overlap floor 1
        self.assertIs(self.mass.floors[1].solid, result.floors[1].solid)

    def test_polygon_points_preserved(self):
        """Original polygon_points document the maximal footprint and must be preserved."""
        config = SubtractionConfig(
            vertical_subtractors=[make_vertical()]
        )
        result = apply_subtractions(self.mass, config)
        self.assertEqual(result.polygon_points, self.mass.polygon_points)

    def test_deactivated_subtractor_leaves_floor_unchanged(self):
        """A vertical subtractor with no snappable face is deactivated → no change."""
        # Gap from top and bottom both exceed 30% of 15 = 4.5
        sub = make_vertical(z_bot=6.0, z_top=9.0)
        config = SubtractionConfig(vertical_subtractors=[sub])
        result = apply_subtractions(self.mass, config)
        for orig, new in zip(self.mass.floors, result.floors):
            self.assertIs(orig.solid, new.solid)


class TestExtractBottomWire(unittest.TestCase):
    """extract_bottom_wire returns a non-null shape for valid floor solids."""

    def setUp(self):
        self.mass = make_mass()

    def test_wire_not_null_for_uncut_floor(self):
        floor = self.mass.floors[0]
        wire = extract_bottom_wire(floor.solid, floor.elevation)
        self.assertFalse(wire.IsNull())

    def test_wire_not_null_after_vertical_cut(self):
        config = SubtractionConfig(vertical_subtractors=[make_vertical()])
        result = apply_subtractions(self.mass, config)
        floor = result.floors[0]
        wire = extract_bottom_wire(floor.solid, floor.elevation)
        self.assertFalse(wire.IsNull())

    def test_wire_at_correct_elevation(self):
        """Wire returned for floor 2 (elevation=6.0) should not be null."""
        floor = self.mass.floors[2]
        wire = extract_bottom_wire(floor.solid, floor.elevation)
        self.assertFalse(wire.IsNull())


if __name__ == "__main__":
    unittest.main(verbosity=2)
