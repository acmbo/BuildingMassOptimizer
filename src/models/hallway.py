from __future__ import annotations

"""
hallway.py — Hallway exploration for building floor plates.

Generates a skeleton-based hallway layout from a floor polygon,
with orthogonalization, grid snapping, core attraction, and travel-
distance validation.
"""

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.spatial import Voronoi
from shapely.geometry import LineString, MultiPolygon, Point, Polygon as ShapelyPolygon
from shapely.geometry.collection import GeometryCollection

from OCC.Core.BRep import BRep_Builder
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCC.Core.gp import gp_Pnt
from OCC.Core.TopoDS import TopoDS_Compound, TopoDS_Shape


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TravelDistanceViolation(Exception):
    """Raised when maximum travel distance is exceeded."""


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------


@dataclass
class HallwayParams:
    """Parameters that govern the hallway layout generation."""

    floor_polygon: list[tuple[float, float]]
    """XY vertices of the floor boundary (no Z)."""

    elevation: float
    """Z elevation of this floor."""

    hallway_width: float = 1.5
    span_x: float = 4.0
    span_y: float = 4.0
    core_locations: list[tuple[float, float]] = field(default_factory=list)
    max_travel_distance: float = 45.0
    snap_tolerance: float = 0.10
    orthog_angle_threshold: float = 22.5  # degrees
    pruning_min_length: float | None = None  # defaults to hallway_width

    def __post_init__(self) -> None:
        if self.pruning_min_length is None:
            self.pruning_min_length = self.hallway_width

        if self.hallway_width <= 0:
            raise ValueError(f"hallway_width must be > 0, got {self.hallway_width}")
        if self.span_x <= 0:
            raise ValueError(f"span_x must be > 0, got {self.span_x}")
        if self.span_y <= 0:
            raise ValueError(f"span_y must be > 0, got {self.span_y}")
        if self.max_travel_distance <= 0:
            raise ValueError(
                f"max_travel_distance must be > 0, got {self.max_travel_distance}"
            )
        if self.snap_tolerance >= self.hallway_width / 2:
            raise ValueError(
                f"snap_tolerance ({self.snap_tolerance}) must be < hallway_width/2 "
                f"({self.hallway_width / 2})"
            )
        if not (0 < self.orthog_angle_threshold < 45):
            raise ValueError(
                f"orthog_angle_threshold must be in (0, 45), "
                f"got {self.orthog_angle_threshold}"
            )
        if len(self.floor_polygon) < 3:
            raise ValueError(
                f"floor_polygon must have at least 3 vertices, "
                f"got {len(self.floor_polygon)}"
            )
        poly_shp = ShapelyPolygon(self.floor_polygon)
        if not poly_shp.is_valid:
            raise ValueError("floor_polygon is not valid (self-intersecting or degenerate).")

    @property
    def grid_origin_x(self) -> float:
        return min(x for x, _ in self.floor_polygon)

    @property
    def grid_origin_y(self) -> float:
        return min(y for _, y in self.floor_polygon)

    @property
    def min_branch_length(self) -> float:
        return self.pruning_min_length  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# SkeletonGraph
# ---------------------------------------------------------------------------


class SkeletonGraph:
    """
    A graph of skeleton nodes and edges representing the hallway centerline.
    """

    def __init__(
        self,
        nodes: list[tuple[float, float]],
        edges: list[tuple[int, int]],
    ) -> None:
        self.nodes: list[tuple[float, float]] = list(nodes)
        self.edges: list[tuple[int, int]] = list(edges)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_medial_axis(cls, polygon: list[tuple[float, float]]) -> "SkeletonGraph":
        """Build a Voronoi-based medial axis skeleton from the floor polygon."""
        poly_shp = ShapelyPolygon(polygon)

        # Sample boundary at ~0.3 m intervals, minimum 30 samples
        perimeter = poly_shp.exterior.length
        n_samples = max(30, int(perimeter / 0.3))
        boundary_pts: list[tuple[float, float]] = []
        for i in range(n_samples):
            pt = poly_shp.exterior.interpolate(i / n_samples, normalized=True)
            boundary_pts.append((pt.x, pt.y))

        sample_arr = np.array(boundary_pts)
        vor = Voronoi(sample_arr)

        # Keep vertices inside polygon
        inside_mask: list[bool] = []
        for v in vor.vertices:
            inside_mask.append(bool(poly_shp.contains(Point(v[0], v[1]))))

        # Build nodes/edges from ridges where both endpoints inside and midpoint inside
        node_map: dict[int, int] = {}  # Voronoi vertex index -> skeleton node index
        nodes: list[tuple[float, float]] = []
        edges: list[tuple[int, int]] = []

        def _get_or_add(vi: int) -> int:
            if vi not in node_map:
                node_map[vi] = len(nodes)
                nodes.append((float(vor.vertices[vi][0]), float(vor.vertices[vi][1])))
            return node_map[vi]

        for ridge in vor.ridge_vertices:
            i0, i1 = ridge
            if i0 < 0 or i1 < 0:
                continue
            if not inside_mask[i0] or not inside_mask[i1]:
                continue
            vx0, vy0 = vor.vertices[i0]
            vx1, vy1 = vor.vertices[i1]
            mx, my = (vx0 + vx1) / 2, (vy0 + vy1) / 2
            if not poly_shp.contains(Point(mx, my)):
                continue
            u = _get_or_add(i0)
            v = _get_or_add(i1)
            if u != v:
                edges.append((u, v))

        return cls(nodes, edges)

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def prune(
        self,
        min_length: float,
        protected_nodes: list[int] | set[int],
    ) -> None:
        """Remove short branches and leaf nodes not in protected set."""
        protected = set(protected_nodes)

        # Remove edges shorter than min_length unless both endpoints are protected
        kept_edges: list[tuple[int, int]] = []
        for u, v in self.edges:
            ux, uy = self.nodes[u]
            vx, vy = self.nodes[v]
            length = math.hypot(vx - ux, vy - uy)
            if length < min_length and not (u in protected and v in protected):
                continue
            kept_edges.append((u, v))
        self.edges = kept_edges

        # Iteratively remove degree-1 leaf nodes not in protected set
        changed = True
        while changed:
            changed = False
            deg: dict[int, int] = defaultdict(int)
            for u, v in self.edges:
                deg[u] += 1
                deg[v] += 1
            new_edges: list[tuple[int, int]] = []
            for u, v in self.edges:
                if (deg[u] == 1 and u not in protected) or (
                    deg[v] == 1 and v not in protected
                ):
                    changed = True
                    continue
                new_edges.append((u, v))
            self.edges = new_edges

        self._compact_nodes()

    def orthogonalize(self, angle_threshold: float, snap_tol: float) -> None:
        """Snap near-axis edges to grid, replace diagonals with L-routes.

        Runs iteratively until no diagonal edges remain.
        """
        for _iteration in range(10):
            threshold_rad = math.radians(angle_threshold)

            x_votes: dict[int, list[float]] = defaultdict(list)
            y_votes: dict[int, list[float]] = defaultdict(list)
            diagonal_edges: list[tuple[int, int]] = []
            axis_edges: list[tuple[int, int]] = []

            for u, v in self.edges:
                ux, uy = self.nodes[u]
                vx, vy = self.nodes[v]
                dx, dy = vx - ux, vy - uy
                length = math.hypot(dx, dy)
                if length < 1e-9:
                    axis_edges.append((u, v))
                    continue
                angle = math.atan2(abs(dy), abs(dx))  # 0=horizontal, pi/2=vertical
                dev = min(angle, math.pi / 2 - angle)

                if dev < threshold_rad:
                    # Near-axis edge: snap
                    axis_edges.append((u, v))
                    if abs(dx) >= abs(dy):
                        # More horizontal — align y
                        avg_y = (uy + vy) / 2
                        y_votes[u].append(avg_y)
                        y_votes[v].append(avg_y)
                    else:
                        # More vertical — align x
                        avg_x = (ux + vx) / 2
                        x_votes[u].append(avg_x)
                        x_votes[v].append(avg_x)
                else:
                    diagonal_edges.append((u, v))

            # Apply votes
            new_nodes = list(self.nodes)
            for i, (x, y) in enumerate(new_nodes):
                nx = float(np.mean(x_votes[i])) if x_votes[i] else x
                ny = float(np.mean(y_votes[i])) if y_votes[i] else y
                new_nodes[i] = (nx, ny)
            self.nodes = new_nodes

            # Replace diagonal edges with L-routes
            new_edges = list(axis_edges)
            for u, v in diagonal_edges:
                ux, uy = self.nodes[u]
                vx, vy = self.nodes[v]
                dx, dy = vx - ux, vy - uy
                if abs(dx) >= abs(dy):
                    corner = (vx, uy)
                else:
                    corner = (ux, vy)
                ci = len(self.nodes)
                self.nodes.append(corner)
                new_edges.append((u, ci))
                new_edges.append((ci, v))
            self.edges = new_edges

            self._merge_close_vertices(snap_tol)

            # Use a slightly larger tolerance on later passes to collapse dense clusters
            merge_tol = min(snap_tol * (1 + _iteration * 0.5), snap_tol * 4)
            self._merge_close_vertices(merge_tol)

            # Convergence: no diagonal edges in this pass
            if not diagonal_edges:
                break

        # Final strict axis-alignment pass using union-find to collapse collinear groups
        # This guarantees exact axis-alignment regardless of chain length
        strict_rad = math.radians(angle_threshold)
        self._force_axis_align(strict_rad)
        self._merge_close_vertices(snap_tol)

    def attract_cores(
        self, core_locations: list[tuple[float, float]], hallway_width: float
    ) -> None:
        """Move skeleton nodes toward core locations or add L-route connections."""
        if not core_locations or not self.nodes:
            return
        for cx, cy in core_locations:
            # Find nearest skeleton node
            best_i, best_dist = -1, float("inf")
            for i, (nx, ny) in enumerate(self.nodes):
                d = math.hypot(nx - cx, ny - cy)
                if d < best_dist:
                    best_dist = d
                    best_i = i

            if best_i < 0:
                continue

            if best_dist <= 2 * hallway_width:
                # Move nearest node to core location
                nx_list = list(self.nodes)
                nx_list[best_i] = (cx, cy)
                self.nodes = nx_list
            else:
                # L-route from nearest node to core
                ux, uy = self.nodes[best_i]
                dx, dy = cx - ux, cy - uy
                if abs(dx) >= abs(dy):
                    corner = (cx, uy)
                else:
                    corner = (ux, cy)
                ci = len(self.nodes)
                core_i = ci + 1
                self.nodes.append(corner)
                self.nodes.append((cx, cy))
                self.edges.append((best_i, ci))
                self.edges.append((ci, core_i))

    def snap_to_grid(
        self,
        span_x: float,
        span_y: float,
        origin: tuple[float, float],
        polygon: list[tuple[float, float]],
    ) -> None:
        """Snap all nodes to the nearest grid intersection inside the polygon."""
        ox, oy = origin
        poly_shp = ShapelyPolygon(polygon)

        new_nodes = list(self.nodes)
        for i, (x, y) in enumerate(new_nodes):
            ix = round((x - ox) / span_x)
            iy = round((y - oy) / span_y)
            snapped = (ox + ix * span_x, oy + iy * span_y)
            if poly_shp.contains(Point(snapped)):
                new_nodes[i] = snapped
            else:
                # Try ±1 neighbors
                best_pt = None
                best_d = float("inf")
                for dix in (-1, 0, 1):
                    for diy in (-1, 0, 1):
                        if dix == 0 and diy == 0:
                            continue
                        candidate = (ox + (ix + dix) * span_x, oy + (iy + diy) * span_y)
                        if poly_shp.contains(Point(candidate)):
                            d = math.hypot(candidate[0] - x, candidate[1] - y)
                            if d < best_d:
                                best_d = d
                                best_pt = candidate
                if best_pt is not None:
                    new_nodes[i] = best_pt
                # else keep original

        self.nodes = new_nodes

        # Remove degenerate edges
        kept: list[tuple[int, int]] = []
        for u, v in self.edges:
            if u == v:
                continue
            ux, uy = self.nodes[u]
            vx, vy = self.nodes[v]
            if math.hypot(vx - ux, vy - uy) < 1e-9:
                continue
            seg = LineString([(ux, uy), (vx, vy)])
            if not poly_shp.intersects(seg):
                continue
            kept.append((u, v))
        self.edges = kept

        self._merge_close_vertices(0.01)

    def is_connected(self) -> bool:
        """Return True if all nodes referenced by edges are in a single component."""
        used = set()
        for u, v in self.edges:
            used.add(u)
            used.add(v)
        if not used:
            return True  # no edges → vacuously connected
        adj: dict[int, list[int]] = defaultdict(list)
        for u, v in self.edges:
            adj[u].append(v)
            adj[v].append(u)
        start = next(iter(used))
        visited = {start}
        queue = deque([start])
        while queue:
            cur = queue.popleft()
            for nb in adj[cur]:
                if nb not in visited:
                    visited.add(nb)
                    queue.append(nb)
        return visited >= used

    def bridge_components(self, polygon: list[tuple[float, float]]) -> None:
        """Connect disconnected components via L-routes inside the polygon."""
        poly_shp = ShapelyPolygon(polygon)
        while not self.is_connected():
            comps = self._connected_components()
            if len(comps) <= 1:
                break
            # Find two closest nodes from different components
            best = (float("inf"), -1, -1)
            for ci_idx in range(len(comps)):
                for cj_idx in range(ci_idx + 1, len(comps)):
                    for ni in comps[ci_idx]:
                        for nj in comps[cj_idx]:
                            xi, yi = self.nodes[ni]
                            xj, yj = self.nodes[nj]
                            d = math.hypot(xj - xi, yj - yi)
                            if d < best[0]:
                                best = (d, ni, nj)
            if best[1] < 0:
                break
            _, ni, nj = best
            xi, yi = self.nodes[ni]
            xj, yj = self.nodes[nj]
            dx, dy = xj - xi, yj - yi
            if abs(dx) >= abs(dy):
                corner = (xj, yi)
            else:
                corner = (xi, yj)
            ci = len(self.nodes)
            self.nodes.append(corner)
            # Check if L-route goes through polygon
            seg1 = LineString([(xi, yi), (corner[0], corner[1])])
            seg2 = LineString([(corner[0], corner[1]), (xj, yj)])
            if poly_shp.intersects(seg1):
                self.edges.append((ni, ci))
            if poly_shp.intersects(seg2):
                self.edges.append((ci, nj))

    def travel_distances(self, core_nodes: list[int]) -> dict[int, float]:
        """Multi-source Dijkstra from core nodes; returns dist per node index."""
        import heapq

        adj: dict[int, list[tuple[float, int]]] = defaultdict(list)
        for u, v in self.edges:
            ux, uy = self.nodes[u]
            vx, vy = self.nodes[v]
            w = math.hypot(vx - ux, vy - uy)
            adj[u].append((w, v))
            adj[v].append((w, u))

        dist: dict[int, float] = {}
        heap: list[tuple[float, int]] = []
        for cn in core_nodes:
            dist[cn] = 0.0
            heapq.heappush(heap, (0.0, cn))

        while heap:
            d, u = heapq.heappop(heap)
            if d > dist.get(u, float("inf")):
                continue
            for w, v in adj[u]:
                nd = d + w
                if nd < dist.get(v, float("inf")):
                    dist[v] = nd
                    heapq.heappush(heap, (nd, v))

        return dist

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _force_axis_align(self, threshold_rad: float) -> None:
        """Force near-axis edges to be exactly axis-aligned using union-find on rows/cols.

        Groups all nodes connected by near-horizontal edges into "Y-groups" and
        sets all their Y-coordinates to the group mean. Similarly for X (vertical edges).
        Iterates until convergence.
        """
        for _ in range(30):
            changed = False
            # Build Y-groups: connected via near-horizontal edges
            parent = list(range(len(self.nodes)))

            def find(x: int) -> int:
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x

            def union(a: int, b: int) -> None:
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[rb] = ra

            y_groups: list[tuple[int, int]] = []  # (u, v) for near-horizontal
            x_groups: list[tuple[int, int]] = []  # (u, v) for near-vertical

            for u, v in self.edges:
                ux, uy = self.nodes[u]
                vx, vy = self.nodes[v]
                dx, dy = vx - ux, vy - uy
                if math.hypot(dx, dy) < 1e-9:
                    continue
                angle = math.atan2(abs(dy), abs(dx))
                dev = min(angle, math.pi / 2 - angle)
                if dev < threshold_rad:
                    if abs(dx) >= abs(dy):
                        y_groups.append((u, v))
                    else:
                        x_groups.append((u, v))

            # Apply Y-groups: all nodes in a y_group get the same Y = mean
            y_parent = list(range(len(self.nodes)))
            def yf(x: int) -> int:
                while y_parent[x] != x:
                    y_parent[x] = y_parent[y_parent[x]]
                    x = y_parent[x]
                return x
            def yu(a: int, b: int) -> None:
                ra, rb = yf(a), yf(b)
                if ra != rb:
                    y_parent[rb] = ra
            for u, v in y_groups:
                yu(u, v)

            y_comp: dict[int, list[float]] = defaultdict(list)
            for i, (x, y) in enumerate(self.nodes):
                y_comp[yf(i)].append(y)
            y_mean: dict[int, float] = {r: float(np.mean(vals)) for r, vals in y_comp.items()}

            x_parent = list(range(len(self.nodes)))
            def xf(x: int) -> int:
                while x_parent[x] != x:
                    x_parent[x] = x_parent[x_parent[x]]
                    x = x_parent[x]
                return x
            def xu(a: int, b: int) -> None:
                ra, rb = xf(a), xf(b)
                if ra != rb:
                    x_parent[rb] = ra
            for u, v in x_groups:
                xu(u, v)

            x_comp: dict[int, list[float]] = defaultdict(list)
            for i, (x, y) in enumerate(self.nodes):
                x_comp[xf(i)].append(x)
            x_mean: dict[int, float] = {r: float(np.mean(vals)) for r, vals in x_comp.items()}

            new_nodes = list(self.nodes)
            for i, (x, y) in enumerate(self.nodes):
                ny = y_mean[yf(i)] if len(y_comp[yf(i)]) > 1 else y
                nx = x_mean[xf(i)] if len(x_comp[xf(i)]) > 1 else x
                if abs(nx - x) > 1e-12 or abs(ny - y) > 1e-12:
                    changed = True
                new_nodes[i] = (nx, ny)
            self.nodes = new_nodes
            if not changed:
                break

    def _compact_nodes(self) -> None:
        """Remove unused nodes, renumber edges accordingly."""
        used = set()
        for u, v in self.edges:
            used.add(u)
            used.add(v)
        old_to_new = {}
        new_nodes = []
        for old_i, node in enumerate(self.nodes):
            if old_i in used:
                old_to_new[old_i] = len(new_nodes)
                new_nodes.append(node)
        self.nodes = new_nodes
        self.edges = [
            (old_to_new[u], old_to_new[v])
            for u, v in self.edges
            if u in old_to_new and v in old_to_new
        ]

    def _merge_close_vertices(self, tol: float) -> None:
        """Union-find merge of nodes within tol, compute centroid, renumber."""
        n = len(self.nodes)
        if n == 0:
            return

        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        # Merge nodes closer than tol
        for i in range(n):
            for j in range(i + 1, n):
                xi, yi = self.nodes[i]
                xj, yj = self.nodes[j]
                if math.hypot(xj - xi, yj - yi) <= tol:
                    union(i, j)

        # Compute representative centroid per component
        groups: dict[int, list[int]] = defaultdict(list)
        for i in range(n):
            groups[find(i)].append(i)

        centroids: dict[int, tuple[float, float]] = {}
        for root, members in groups.items():
            cx = sum(self.nodes[m][0] for m in members) / len(members)
            cy = sum(self.nodes[m][1] for m in members) / len(members)
            centroids[root] = (cx, cy)

        # Build new node list
        root_to_new: dict[int, int] = {}
        new_nodes: list[tuple[float, float]] = []
        for i in range(n):
            r = find(i)
            if r not in root_to_new:
                root_to_new[r] = len(new_nodes)
                new_nodes.append(centroids[r])

        # Remap edges, drop self-loops, deduplicate
        new_edges_set: set[tuple[int, int]] = set()
        for u, v in self.edges:
            nu = root_to_new[find(u)]
            nv = root_to_new[find(v)]
            if nu == nv:
                continue
            edge = (min(nu, nv), max(nu, nv))
            new_edges_set.add(edge)

        self.nodes = new_nodes
        self.edges = list(new_edges_set)

    def _connected_components(self) -> list[list[int]]:
        """Return list of node-index lists per connected component."""
        used = set()
        for u, v in self.edges:
            used.add(u)
            used.add(v)

        adj: dict[int, list[int]] = defaultdict(list)
        for u, v in self.edges:
            adj[u].append(v)
            adj[v].append(u)

        visited: set[int] = set()
        components: list[list[int]] = []
        for start in used:
            if start in visited:
                continue
            comp: list[int] = []
            queue = deque([start])
            visited.add(start)
            while queue:
                cur = queue.popleft()
                comp.append(cur)
                for nb in adj[cur]:
                    if nb not in visited:
                        visited.add(nb)
                        queue.append(nb)
            components.append(comp)
        return components


# ---------------------------------------------------------------------------
# OCC helper
# ---------------------------------------------------------------------------


def _shapely_polygon_to_occ(shp: Any, elevation: float) -> TopoDS_Shape:
    """Convert a shapely Polygon or MultiPolygon to an OCC compound of faces."""
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)

    if shp is None or shp.is_empty:
        return compound

    # Collect individual polygons
    if isinstance(shp, (MultiPolygon, GeometryCollection)):
        polys = [g for g in shp.geoms if isinstance(g, ShapelyPolygon) and not g.is_empty]
    elif isinstance(shp, ShapelyPolygon):
        polys = [shp]
    else:
        return compound

    faces_added = 0
    single_face = None

    for poly in polys:
        coords = list(poly.exterior.coords)[:-1]  # skip closing duplicate
        if len(coords) < 3:
            continue

        maker = BRepBuilderAPI_MakePolygon()
        for x, y in coords:
            maker.Add(gp_Pnt(x, y, elevation))
        maker.Close()
        if not maker.IsDone():
            continue
        wire = maker.Wire()

        face_maker = BRepBuilderAPI_MakeFace(wire)
        if not face_maker.IsDone():
            continue
        face = face_maker.Face()
        builder.Add(compound, face)
        single_face = face
        faces_added += 1

    if faces_added == 1 and single_face is not None:
        return single_face
    return compound


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------


def _find_core_indices(
    skeleton: SkeletonGraph,
    core_locations: list[tuple[float, float]],
    max_dist: float,
) -> list[int]:
    """Find skeleton node indices nearest to each core, within max_dist."""
    result: list[int] = []
    seen: set[int] = set()
    for cx, cy in core_locations:
        best_i, best_d = -1, float("inf")
        for i, (nx, ny) in enumerate(skeleton.nodes):
            d = math.hypot(nx - cx, ny - cy)
            if d < best_d:
                best_d = d
                best_i = i
        if best_i >= 0 and best_d <= max_dist and best_i not in seen:
            result.append(best_i)
            seen.add(best_i)
    return result


# ---------------------------------------------------------------------------
# HallwayLayout
# ---------------------------------------------------------------------------


@dataclass
class HallwayLayout:
    """Result of hallway generation: skeleton + OCC shapes + metrics."""

    params: HallwayParams
    skeleton: SkeletonGraph
    hallway_polygon: TopoDS_Shape
    room_zone: TopoDS_Shape
    hallway_shp: Any = field(repr=False)
    floor_shp: Any = field(repr=False)
    floor_area: float = field(repr=False)
    hallway_area: float = field(repr=False)
    room_area: float = field(repr=False)

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    @classmethod
    def generate(cls, params: HallwayParams) -> "HallwayLayout":
        """Full 8-step pipeline to produce a HallwayLayout."""
        poly = params.floor_polygon
        floor_shp = ShapelyPolygon(poly)
        floor_area = floor_shp.area
        half_w = params.hallway_width / 2

        # Step 1: Build raw skeleton
        skeleton = SkeletonGraph.from_medial_axis(poly)

        # Step 2: Protected indices (near any core location)
        protected: list[int] = []
        for cx, cy in params.core_locations:
            for i, (nx, ny) in enumerate(skeleton.nodes):
                if math.hypot(nx - cx, ny - cy) <= 2 * params.hallway_width:
                    protected.append(i)

        # Step 3: Prune
        skeleton.prune(params.pruning_min_length, protected)  # type: ignore[arg-type]

        # Step 4: Orthogonalize
        skeleton.orthogonalize(params.orthog_angle_threshold, params.snap_tolerance)

        # Step 5: Attract cores
        skeleton.attract_cores(params.core_locations, params.hallway_width)

        # Step 6: Snap to grid
        skeleton.snap_to_grid(
            params.span_x,
            params.span_y,
            (params.grid_origin_x, params.grid_origin_y),
            poly,
        )

        # Step 7: Bridge disconnected components
        if params.core_locations and not skeleton.is_connected():
            skeleton.bridge_components(poly)

        # Cleanup: remove near-zero edges (artifacts from grid snapping).
        # Do NOT use prune() here — its iterative leaf-removal phase would
        # cascade and collapse the entire skeleton on non-branching shapes
        # (chains, L-shapes, etc.) because all endpoints are unprotected leaves.
        # A direct edge filter is sufficient: snap_to_grid already handles
        # node merging via _merge_close_vertices.
        skeleton.edges = [
            (u, v) for u, v in skeleton.edges
            if math.hypot(
                skeleton.nodes[v][0] - skeleton.nodes[u][0],
                skeleton.nodes[v][1] - skeleton.nodes[u][1],
            ) >= 0.05
        ]
        skeleton._compact_nodes()

        # Edge case: no edges after processing → create minimal cross spine
        if not skeleton.edges:
            centroid = floor_shp.centroid
            cx_c, cy_c = centroid.x, centroid.y
            # Find boundary intersections along horizontal and vertical lines
            h_line = LineString([(floor_shp.bounds[0] - 1, cy_c), (floor_shp.bounds[2] + 1, cy_c)])
            v_line = LineString([(cx_c, floor_shp.bounds[1] - 1), (cx_c, floor_shp.bounds[3] + 1)])
            nodes = [(cx_c, cy_c)]
            edges = []
            for line in (h_line, v_line):
                inter = floor_shp.exterior.intersection(line)
                if hasattr(inter, "geoms"):
                    pts = list(inter.geoms)
                else:
                    pts = [inter] if not inter.is_empty else []
                for pt in pts[:2]:
                    ni = len(nodes)
                    nodes.append((pt.x, pt.y))
                    edges.append((0, ni))
            skeleton.nodes = nodes
            skeleton.edges = edges

        # Step 8: Buffer skeleton edges → hallway shape
        lines = []
        for u, v in skeleton.edges:
            ux, uy = skeleton.nodes[u]
            vx, vy = skeleton.nodes[v]
            if math.hypot(vx - ux, vy - uy) < 1e-9:
                continue
            lines.append(LineString([(ux, uy), (vx, vy)]))

        if lines:
            from shapely.ops import unary_union
            buffered = unary_union([ln.buffer(half_w, cap_style=2) for ln in lines])
            hallway_shp = buffered.intersection(floor_shp)
        else:
            hallway_shp = floor_shp.buffer(0)

        room_shp = floor_shp.difference(hallway_shp)

        # Travel distance check
        core_indices = _find_core_indices(skeleton, params.core_locations, params.hallway_width * 3)
        if params.core_locations and core_indices:
            dist_map = skeleton.travel_distances(core_indices)
            worst_node = -1
            worst_dist = -1.0
            for ni, d in dist_map.items():
                total = d + half_w
                if total > worst_dist:
                    worst_dist = total
                    worst_node = ni
            if worst_dist > params.max_travel_distance:
                loc = skeleton.nodes[worst_node] if worst_node >= 0 else (0.0, 0.0)
                raise TravelDistanceViolation(
                    f"Max travel distance {worst_dist:.2f} m exceeds limit "
                    f"{params.max_travel_distance} m at node {loc}"
                )

        # Convert to OCC shapes
        hallway_occ = _shapely_polygon_to_occ(hallway_shp, params.elevation)
        room_occ = _shapely_polygon_to_occ(room_shp, params.elevation)

        hallway_area = hallway_shp.area
        room_area = room_shp.area

        return cls(
            params=params,
            skeleton=skeleton,
            hallway_polygon=hallway_occ,
            room_zone=room_occ,
            hallway_shp=hallway_shp,
            floor_shp=floor_shp,
            floor_area=floor_area,
            hallway_area=hallway_area,
            room_area=room_area,
        )

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def max_travel_distance_actual(self) -> float:
        """Return the maximum travel distance from any skeleton node to nearest core."""
        core_indices = _find_core_indices(
            self.skeleton,
            self.params.core_locations,
            self.params.hallway_width * 3,
        )
        if not core_indices:
            return 0.0
        dist_map = self.skeleton.travel_distances(core_indices)
        if not dist_map:
            return 0.0
        return max(dist_map.values()) + self.params.hallway_width / 2

    def hallway_area_ratio(self) -> float:
        """Return hallway_area / floor_area."""
        if self.floor_area == 0:
            return 0.0
        return self.hallway_area / self.floor_area

    def validate(self) -> list[str]:
        """Return list of violation strings; empty list means pass."""
        violations: list[str] = []

        # FR-10: area conservation
        if abs(self.hallway_area + self.room_area - self.floor_area) >= 1e-4:
            violations.append(
                f"FR-10 area conservation failed: "
                f"hallway ({self.hallway_area:.4f}) + room ({self.room_area:.4f}) "
                f"!= floor ({self.floor_area:.4f})"
            )

        # FR-6: hallway within floor
        if not self.hallway_shp.within(self.floor_shp.buffer(1e-3)):
            violations.append("FR-6: hallway_shp is not within floor boundary.")

        # FR-9: no near-degenerate leaf skeleton edges (shorter than snap_tolerance)
        # Short interior connector edges (e.g. at concave corners after snapping) are OK
        snap_tol = self.params.snap_tolerance
        deg: dict[int, int] = defaultdict(int)
        for u, v in self.skeleton.edges:
            deg[u] += 1
            deg[v] += 1
        for u, v in self.skeleton.edges:
            ux, uy = self.skeleton.nodes[u]
            vx, vy = self.skeleton.nodes[v]
            length = math.hypot(vx - ux, vy - uy)
            # Flag only truly degenerate leaf edges (shorter than snap_tolerance)
            if length < snap_tol and (deg[u] == 1 or deg[v] == 1):
                violations.append(
                    f"FR-9: skeleton edge ({u},{v}) length {length:.3f} < "
                    f"snap_tolerance ({snap_tol:.3f})"
                )

        return violations
