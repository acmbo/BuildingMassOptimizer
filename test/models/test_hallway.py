"""
Unit tests for hallway.py — HallwayParams, SkeletonGraph, HallwayLayout.

Run from project root:
    conda run -n pyoccEnv python -m pytest test/models/test_hallway.py -v
"""
from __future__ import annotations

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from shapely.geometry import Polygon as ShapelyPolygon

from models.building_mass import BuildingMass
from models.hallway import (
    HallwayLayout,
    HallwayParams,
    SkeletonGraph,
    TravelDistanceViolation,
)
from models.hallway_engine import apply_hallway_to_floor, apply_hallway_to_mass

# ---------------------------------------------------------------------------
# Shared polygon fixtures
# ---------------------------------------------------------------------------

RECT_POLY = [(0, 0), (20, 0), (20, 10), (0, 10)]
L_POLY = [(0, 0), (20, 0), (20, 10), (10, 10), (10, 20), (0, 20)]
T_POLY = [(0, 5), (10, 5), (10, 0), (20, 0), (20, 5), (30, 5), (30, 15), (0, 15)]
U_POLY = [(0, 0), (8, 0), (8, 10), (12, 10), (12, 0), (20, 0), (20, 20), (0, 20)]
IRR_POLY = [(5, 0), (15, 0), (20, 5), (20, 15), (15, 20), (5, 20), (0, 10)]

ALL_POLYS = [RECT_POLY, L_POLY, T_POLY, U_POLY, IRR_POLY]
ALL_POLY_NAMES = ["rect", "L", "T", "U", "irregular"]


def _make_params(poly, **kwargs):
    defaults = dict(elevation=0.0, hallway_width=1.5, span_x=4.0, span_y=4.0)
    defaults.update(kwargs)
    return HallwayParams(floor_polygon=poly, **defaults)


# ---------------------------------------------------------------------------
# TestHallwayParams
# ---------------------------------------------------------------------------


class TestHallwayParams(unittest.TestCase):
    def test_valid_defaults(self):
        p = HallwayParams(floor_polygon=RECT_POLY, elevation=0.0)
        self.assertEqual(p.hallway_width, 1.5)
        self.assertEqual(p.pruning_min_length, 1.5)

    def test_pruning_min_length_default_equals_hallway_width(self):
        p = HallwayParams(floor_polygon=RECT_POLY, elevation=0.0, hallway_width=2.0)
        self.assertEqual(p.pruning_min_length, 2.0)

    def test_pruning_min_length_explicit(self):
        p = HallwayParams(
            floor_polygon=RECT_POLY, elevation=0.0, hallway_width=2.0, pruning_min_length=3.0
        )
        self.assertEqual(p.pruning_min_length, 3.0)

    def test_grid_origin_properties(self):
        p = HallwayParams(floor_polygon=RECT_POLY, elevation=0.0)
        self.assertEqual(p.grid_origin_x, 0.0)
        self.assertEqual(p.grid_origin_y, 0.0)

    def test_min_branch_length_alias(self):
        p = HallwayParams(floor_polygon=RECT_POLY, elevation=0.0, pruning_min_length=2.5)
        self.assertEqual(p.min_branch_length, 2.5)

    def test_invalid_hallway_width(self):
        with self.assertRaises(ValueError):
            HallwayParams(floor_polygon=RECT_POLY, elevation=0.0, hallway_width=0.0)

    def test_invalid_span_x(self):
        with self.assertRaises(ValueError):
            HallwayParams(floor_polygon=RECT_POLY, elevation=0.0, span_x=-1.0)

    def test_invalid_snap_tolerance(self):
        # snap_tol >= hallway_width/2 should raise
        with self.assertRaises(ValueError):
            HallwayParams(
                floor_polygon=RECT_POLY, elevation=0.0, hallway_width=1.5, snap_tolerance=0.75
            )

    def test_invalid_angle_threshold_zero(self):
        with self.assertRaises(ValueError):
            HallwayParams(
                floor_polygon=RECT_POLY, elevation=0.0, orthog_angle_threshold=0.0
            )

    def test_invalid_angle_threshold_45(self):
        with self.assertRaises(ValueError):
            HallwayParams(
                floor_polygon=RECT_POLY, elevation=0.0, orthog_angle_threshold=45.0
            )

    def test_invalid_polygon_too_few_vertices(self):
        with self.assertRaises(ValueError):
            HallwayParams(floor_polygon=[(0, 0), (1, 0)], elevation=0.0)

    def test_invalid_polygon_self_intersecting(self):
        bowtie = [(0, 0), (10, 10), (10, 0), (0, 10)]  # self-intersecting
        with self.assertRaises(ValueError):
            HallwayParams(floor_polygon=bowtie, elevation=0.0)


# ---------------------------------------------------------------------------
# QG-1: All polygon types generate without exception and validate() == []
# ---------------------------------------------------------------------------


class TestQG1_PolygonTypes(unittest.TestCase):
    def _run_for(self, poly):
        params = _make_params(poly)
        layout = HallwayLayout.generate(params)
        violations = layout.validate()
        self.assertEqual(violations, [], f"validate() violations: {violations}")

    def test_rectangle(self):
        self._run_for(RECT_POLY)

    def test_l_shape(self):
        self._run_for(L_POLY)

    def test_t_shape(self):
        self._run_for(T_POLY)

    def test_u_shape(self):
        self._run_for(U_POLY)

    def test_irregular(self):
        self._run_for(IRR_POLY)


# ---------------------------------------------------------------------------
# QG-2: Hallway stays within floor boundary
# ---------------------------------------------------------------------------


class TestQG2_BoundarySafety(unittest.TestCase):
    def _run_for(self, poly):
        params = _make_params(poly)
        layout = HallwayLayout.generate(params)
        floor_shp = ShapelyPolygon(poly)
        self.assertTrue(
            layout.hallway_shp.within(floor_shp.buffer(1e-3)),
            "hallway_shp extends outside floor boundary",
        )

    def test_rectangle(self):
        self._run_for(RECT_POLY)

    def test_l_shape(self):
        self._run_for(L_POLY)

    def test_t_shape(self):
        self._run_for(T_POLY)

    def test_u_shape(self):
        self._run_for(U_POLY)

    def test_irregular(self):
        self._run_for(IRR_POLY)


# ---------------------------------------------------------------------------
# QG-3: Area conservation
# ---------------------------------------------------------------------------


class TestQG3_AreaConservation(unittest.TestCase):
    def _run_for(self, poly):
        params = _make_params(poly)
        layout = HallwayLayout.generate(params)
        self.assertAlmostEqual(
            layout.hallway_area + layout.room_area,
            layout.floor_area,
            delta=1e-4,
            msg="Area conservation violated",
        )

    def test_rectangle(self):
        self._run_for(RECT_POLY)

    def test_l_shape(self):
        self._run_for(L_POLY)

    def test_t_shape(self):
        self._run_for(T_POLY)

    def test_u_shape(self):
        self._run_for(U_POLY)

    def test_irregular(self):
        self._run_for(IRR_POLY)


# ---------------------------------------------------------------------------
# QG-4: Minimum hallway area ratio > 0
# ---------------------------------------------------------------------------


class TestQG4_MinimumWidth(unittest.TestCase):
    def test_rectangle_positive_ratio(self):
        params = _make_params(RECT_POLY)
        layout = HallwayLayout.generate(params)
        self.assertGreater(layout.hallway_area_ratio(), 0.0)


# ---------------------------------------------------------------------------
# QG-5: Orthogonality after orthogonalize()
# ---------------------------------------------------------------------------


class TestQG5_Orthogonality(unittest.TestCase):
    def test_all_edges_axis_aligned_after_orthogonalize(self):
        skeleton = SkeletonGraph.from_medial_axis(RECT_POLY)
        skeleton.orthogonalize(22.5, 0.10)
        tol = math.radians(0.5)
        for u, v in skeleton.edges:
            ux, uy = skeleton.nodes[u]
            vx, vy = skeleton.nodes[v]
            dx, dy = vx - ux, vy - uy
            if math.hypot(dx, dy) < 1e-9:
                continue
            angle = math.atan2(abs(dy), abs(dx))
            dev = min(angle, math.pi / 2 - angle)
            self.assertLess(
                dev,
                tol,
                f"Edge ({u},{v}) not axis-aligned: angle={math.degrees(angle):.2f}°",
            )


# ---------------------------------------------------------------------------
# QG-6: Core connectivity
# ---------------------------------------------------------------------------


class TestQG6_CoreConnectivity(unittest.TestCase):
    def test_rectangle_with_center_core(self):
        params = _make_params(RECT_POLY, core_locations=[(10.0, 5.0)])
        layout = HallwayLayout.generate(params)
        self.assertTrue(layout.skeleton.is_connected())


# ---------------------------------------------------------------------------
# QG-7: Travel distance <= limit
# ---------------------------------------------------------------------------


class TestQG7_TravelDistance(unittest.TestCase):
    def test_20x10_center_core_15m_limit(self):
        params = _make_params(
            RECT_POLY,
            core_locations=[(10.0, 5.0)],
            max_travel_distance=15.0,
        )
        layout = HallwayLayout.generate(params)
        actual = layout.max_travel_distance_actual()
        self.assertLessEqual(actual, 15.0)


# ---------------------------------------------------------------------------
# QG-8: Pruning removes short leaf branches
# ---------------------------------------------------------------------------


class TestQG8_Pruning(unittest.TestCase):
    def test_no_short_leaf_branches(self):
        skeleton = SkeletonGraph.from_medial_axis(RECT_POLY)
        min_len = 2.0
        skeleton.prune(min_len, [])
        # After pruning: no node should be degree-1 with edge length < min_len
        from collections import defaultdict

        deg: dict[int, int] = defaultdict(int)
        for u, v in skeleton.edges:
            deg[u] += 1
            deg[v] += 1
        for u, v in skeleton.edges:
            ux, uy = skeleton.nodes[u]
            vx, vy = skeleton.nodes[v]
            length = math.hypot(vx - ux, vy - uy)
            if length < min_len:
                # Both endpoints must have degree > 1 (not leaves)
                self.assertGreater(deg[u], 1, f"Short edge ({u},{v}) with leaf endpoint {u}")
                self.assertGreater(deg[v], 1, f"Short edge ({u},{v}) with leaf endpoint {v}")


# ---------------------------------------------------------------------------
# QG-9: Grid alignment after snap_to_grid()
# ---------------------------------------------------------------------------


class TestQG9_GridAlignment(unittest.TestCase):
    def test_nodes_on_grid(self):
        span_x, span_y = 4.0, 4.0
        origin = (0.0, 0.0)
        skeleton = SkeletonGraph.from_medial_axis(RECT_POLY)
        skeleton.snap_to_grid(span_x, span_y, origin, RECT_POLY)

        tol = 0.10 + 1e-9
        for i, (x, y) in enumerate(skeleton.nodes):
            rx = (x - origin[0]) % span_x
            ry = (y - origin[1]) % span_y
            # At least one axis snapped to grid
            x_ok = min(rx, span_x - rx) < tol
            y_ok = min(ry, span_y - ry) < tol
            self.assertTrue(
                x_ok or y_ok,
                f"Node {i} ({x:.3f}, {y:.3f}) not grid-aligned: rx={rx:.3f}, ry={ry:.3f}",
            )


# ---------------------------------------------------------------------------
# QG-10: Full pipeline 20x20, 4x4, 2 cores
# ---------------------------------------------------------------------------


class TestQG10_FullPipeline(unittest.TestCase):
    def test_20x20_two_cores(self):
        poly = [(0, 0), (20, 0), (20, 20), (0, 20)]
        params = HallwayParams(
            floor_polygon=poly,
            elevation=0.0,
            hallway_width=1.8,
            span_x=4.0,
            span_y=4.0,
            core_locations=[(4.0, 4.0), (16.0, 16.0)],
            max_travel_distance=45.0,
        )
        layout = HallwayLayout.generate(params)
        violations = layout.validate()
        self.assertEqual(violations, [])
        self.assertLess(layout.hallway_area_ratio(), 0.30)
        self.assertLessEqual(
            layout.max_travel_distance_actual(), params.max_travel_distance
        )


# ---------------------------------------------------------------------------
# QG-11: L-shape hallway stays within floor
# ---------------------------------------------------------------------------


class TestQG11_CornerProblem(unittest.TestCase):
    def test_l_shape_within_floor(self):
        params = _make_params(L_POLY)
        layout = HallwayLayout.generate(params)
        floor_shp = ShapelyPolygon(L_POLY)
        self.assertTrue(
            layout.hallway_shp.within(floor_shp.buffer(1e-3)),
            "L-shape hallway extends outside floor boundary",
        )


# ---------------------------------------------------------------------------
# QG-12: TravelDistanceViolation for long thin polygon
# ---------------------------------------------------------------------------


class TestQG12_TravelDistanceViolation(unittest.TestCase):
    def test_long_thin_polygon_raises(self):
        poly = [(0, 0), (80, 0), (80, 5), (0, 5)]
        params = HallwayParams(
            floor_polygon=poly,
            elevation=0.0,
            hallway_width=1.5,
            span_x=4.0,
            span_y=4.0,
            core_locations=[(1.0, 2.5)],
            max_travel_distance=10.0,
        )
        with self.assertRaises(TravelDistanceViolation) as ctx:
            HallwayLayout.generate(params)
        # Message should contain a location tuple-like string
        msg = str(ctx.exception)
        self.assertIn("node", msg.lower())


# ---------------------------------------------------------------------------
# HallwayEngine — apply_hallway_to_floor / apply_hallway_to_mass
# ---------------------------------------------------------------------------


class TestHallwayEngine(unittest.TestCase):
    """Tests for hallway_engine.py."""

    def _base_params(self, polygon, elevation=0.0):
        return HallwayParams(
            floor_polygon=polygon,
            elevation=elevation,
            hallway_width=1.8,
            span_x=4.0,
            span_y=4.0,
            core_locations=[(10.0, 5.0)],
            max_travel_distance=45.0,
        )

    # -- apply_hallway_to_floor --------------------------------------------

    def test_apply_to_floor_sets_hallway(self):
        """floor.hallway is None before and HallwayLayout after the call."""
        mass = BuildingMass.create(
            [(0, 0, 0), (20, 0, 0), (20, 10, 0), (0, 10, 0)],
            floor_height=3.0,
            num_floors=1,
        )
        floor = mass.floors[0]
        self.assertIsNone(floor.hallway)

        params = self._base_params(RECT_POLY)
        apply_hallway_to_floor(floor, params)

        self.assertIsInstance(floor.hallway, HallwayLayout)

    def test_apply_to_floor_returns_same_floor(self):
        mass = BuildingMass.create(
            [(0, 0, 0), (20, 0, 0), (20, 10, 0), (0, 10, 0)],
            floor_height=3.0,
            num_floors=1,
        )
        floor = mass.floors[0]
        params = self._base_params(RECT_POLY)
        result = apply_hallway_to_floor(floor, params)
        self.assertIs(result, floor)

    def test_apply_to_floor_hallway_shp_not_empty(self):
        mass = BuildingMass.create(
            [(0, 0, 0), (20, 0, 0), (20, 10, 0), (0, 10, 0)],
            floor_height=3.0,
            num_floors=1,
        )
        floor = mass.floors[0]
        params = self._base_params(RECT_POLY)
        apply_hallway_to_floor(floor, params)
        self.assertFalse(floor.hallway.hallway_shp.is_empty)

    # -- apply_hallway_to_mass ---------------------------------------------

    def test_apply_to_mass_all_floors_get_hallway(self):
        """Every floor of a 3-floor mass has a HallwayLayout after the call."""
        mass = BuildingMass.create(
            [(0, 0, 0), (20, 0, 0), (20, 10, 0), (0, 10, 0)],
            floor_height=3.0,
            num_floors=3,
        )
        for floor in mass.floors:
            self.assertIsNone(floor.hallway)

        params = self._base_params(RECT_POLY)
        apply_hallway_to_mass(mass, params)

        for floor in mass.floors:
            self.assertIsInstance(floor.hallway, HallwayLayout)

    def test_apply_to_mass_returns_same_mass(self):
        mass = BuildingMass.create(
            [(0, 0, 0), (20, 0, 0), (20, 10, 0), (0, 10, 0)],
            floor_height=3.0,
            num_floors=2,
        )
        params = self._base_params(RECT_POLY)
        result = apply_hallway_to_mass(mass, params)
        self.assertIs(result, mass)

    def test_apply_to_mass_elevation_matches_floor(self):
        """Each floor's HallwayLayout.params.elevation must equal the floor elevation."""
        mass = BuildingMass.create(
            [(0, 0, 0), (20, 0, 0), (20, 10, 0), (0, 10, 0)],
            floor_height=3.0,
            num_floors=4,
        )
        params = self._base_params(RECT_POLY, elevation=0.0)
        apply_hallway_to_mass(mass, params)
        for floor in mass.floors:
            self.assertAlmostEqual(
                floor.hallway.params.elevation,
                floor.elevation,
                places=9,
            )

    def test_apply_to_mass_per_floor_polygons(self):
        """per_floor_polygons overrides the polygon for each floor independently."""
        poly_a = [(0, 0), (20, 0), (20, 10), (0, 10)]
        poly_b = [(0, 0), (15, 0), (15, 10), (0, 10)]
        mass = BuildingMass.create(
            [(0, 0, 0), (20, 0, 0), (20, 10, 0), (0, 10, 0)],
            floor_height=3.0,
            num_floors=2,
        )
        params = self._base_params(poly_a)
        apply_hallway_to_mass(mass, params, per_floor_polygons=[poly_a, poly_b])

        self.assertEqual(mass.floors[0].hallway.params.floor_polygon, poly_a)
        self.assertEqual(mass.floors[1].hallway.params.floor_polygon, poly_b)

    def test_individuum_floors_untouched_without_engine(self):
        """Floors created via BuildingMass.create() have hallway=None by default."""
        mass = BuildingMass.create(
            [(0, 0, 0), (20, 0, 0), (20, 10, 0), (0, 10, 0)],
            floor_height=3.0,
            num_floors=5,
        )
        for floor in mass.floors:
            self.assertIsNone(floor.hallway)


if __name__ == "__main__":
    unittest.main()
