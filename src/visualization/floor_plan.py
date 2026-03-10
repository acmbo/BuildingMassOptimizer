"""
Architectural floor plan visualization.

Public API
----------
draw_floor_plan(ax, floor, ...)
    Render one FloorData as an architectural section-cut plan into an Axes.

draw_floor_plan_grid(floors, ...)
    Compose multiple floor plans into a matplotlib figure (one subplot per floor).

Design conventions used (thinking like an architect)
------------------------------------------------------
A floor plan is a horizontal section cut ~1 m above the floor slab.  The
image is read in two visual passes:

  1. The outer building perimeter — heaviest line weight — defines the
     building's relationship to the site.
  2. The interior — floor fill with diagonal hatch, white voids, service
     cores — describes usable area and absent material.

Line-weight hierarchy (from heaviest to lightest):
  heavy   1.8 pt  outer building boundary (the section cut through external walls)
  medium  1.0 pt  courtyard / void boundaries, core outlines
  light   0.25 pt column grid lines (always recede behind everything else)
  hairline 0.35 pt hatch lines over solid floor fill

The column grid is the structural skeleton visible to the architect.
Column lines are drawn as thin dash-dot lines spanning the full plan;
column positions are marked with filled dots at every grid intersection.
Dots outside the building footprint are rendered at 35 % opacity (they
structurally exist but are outside the building envelope).
"""

from __future__ import annotations

import math

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from matplotlib.path import Path
from matplotlib.patches import PathPatch

from models.wire_utils import extract_wire_loops
from visualization.palette import merge_palette
from visualization.scale_bar import draw_scale_bar, draw_north_arrow


# ──────────────────────────────────────────────────────────────────────────────
# Internal geometry helpers
# ──────────────────────────────────────────────────────────────────────────────

def _xy_loops(wire_shape) -> list[list[tuple[float, float]]]:
    """Extract 2-D (x, y) loops from a floor wire or compound of wires."""
    return [
        [(p[0], p[1]) for p in loop]
        for loop in extract_wire_loops(wire_shape)
    ]


def _build_combined_path(xy_loops: list[list[tuple[float, float]]]) -> Path:
    """
    Build a matplotlib Path encoding outer loop + hole loops.

    Hole loops (index > 0) are reversed so their winding is opposite to the
    outer loop.  matplotlib's non-zero winding rule then punches them as holes
    through both fill and hatch.
    """
    verts: list = []
    codes: list = []
    for i, xy in enumerate(xy_loops):
        pts = list(reversed(xy)) if i > 0 else list(xy)
        for j, pt in enumerate(pts):
            verts.append(pt)
            codes.append(Path.MOVETO if j == 0 else Path.LINETO)
        verts.append(pts[0])
        codes.append(Path.CLOSEPOLY)
    return Path(np.array(verts, dtype=float), codes)


def _simple_path(xy: list[tuple[float, float]]) -> Path:
    """Closed matplotlib Path for a single 2-D loop."""
    pts = list(xy)
    verts = pts + [pts[0]]
    codes = [Path.MOVETO] + [Path.LINETO] * (len(pts) - 1) + [Path.CLOSEPOLY]
    return Path(np.array(verts, dtype=float), codes)


# ──────────────────────────────────────────────────────────────────────────────
# Primary single-floor drawing function
# ──────────────────────────────────────────────────────────────────────────────

def draw_floor_plan(
    ax: "matplotlib.axes.Axes",
    floor,
    *,
    column_grid=None,
    original_footprint: list[tuple[float, float]] | None = None,
    show_column_labels: bool = True,
    show_scale_bar: bool = True,
    show_north_arrow: bool = False,
    show_floor_label: bool = True,
    margin: float = 3.5,
    palette: dict | None = None,
) -> None:
    """
    Render one FloorData as an architectural section-cut floor plan.

    All drawing layers are applied in strict Z-order so later layers always
    sit on top.  The caller is responsible for figure creation, layout, and
    plt.show() / figure.savefig().

    Parameters
    ----------
    ax
        Target matplotlib Axes (must already exist).
    floor
        FloorData to visualize.  Reads ``polygon_wire`` and ``cores``.
    column_grid
        ColumnGrid — if provided, grid lines and column dots are overlaid.
    original_footprint
        XY points of the un-subtracted building outline.  Drawn as a dashed
        reference so the viewer can see which material was removed.
    show_column_labels
        Numeric labels along X (1, 2, 3 …) and alphabetic labels along Y
        (A, B, C …) placed outside the footprint in the margin zone.
    show_scale_bar
        Draw a 5 m segmented scale bar in the lower-left corner.
    show_north_arrow
        Draw a ↑ N north arrow in the upper-right corner.
    show_floor_label
        Set axes title to "Floor n   z = z.z m".
    margin
        Extra space (model metres) added around the footprint bounding box.
    palette
        Color overrides merged with DEFAULT_PALETTE.
    """
    pal = merge_palette(palette)

    # ── Axes setup ────────────────────────────────────────────────────────────
    ax.set_aspect("equal")
    ax.set_facecolor(pal["PAPER"])
    ax.set_axis_off()

    # ── Geometry extraction ───────────────────────────────────────────────────
    loops = _xy_loops(floor.polygon_wire)

    # Compute axis limits from all available point data
    all_pts: list[tuple[float, float]] = [pt for loop in loops for pt in loop]
    if original_footprint:
        all_pts.extend(original_footprint)
    if not all_pts:
        return

    xmin_d = min(p[0] for p in all_pts)
    xmax_d = max(p[0] for p in all_pts)
    ymin_d = min(p[1] for p in all_pts)
    ymax_d = max(p[1] for p in all_pts)

    xlim = (xmin_d - margin, xmax_d + margin)
    ylim = (ymin_d - margin, ymax_d + margin)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)

    # ── Layer 2 — original footprint dashed reference ─────────────────────────
    if original_footprint:
        orig = list(original_footprint) + [original_footprint[0]]
        xs, ys = zip(*orig)
        ax.plot(
            xs, ys,
            color=pal["ORIG_FOOTPRINT"], linewidth=0.8, linestyle="--",
            alpha=0.65, zorder=2,
        )

    # ── Layer 3 — column grid lines ───────────────────────────────────────────
    if column_grid is not None:
        dash_dot = (0, (8, 4, 2, 4))
        for gx in column_grid.grid_lines_x:
            ax.plot(
                [gx, gx], [ylim[0], ylim[1]],
                color=pal["GRID_LINE"], linewidth=0.25,
                linestyle=dash_dot, alpha=0.9, zorder=3,
            )
        for gy in column_grid.grid_lines_y:
            ax.plot(
                [xlim[0], xlim[1]], [gy, gy],
                color=pal["GRID_LINE"], linewidth=0.25,
                linestyle=dash_dot, alpha=0.9, zorder=3,
            )

    # ── Layers 4+5 — floor solid fill + diagonal hatch ───────────────────────
    if loops:
        combined = _build_combined_path(loops)

        # Solid fill (winding rule punches holes automatically)
        ax.add_patch(PathPatch(
            combined,
            facecolor=pal["FLOOR_FILL"], edgecolor="none",
            zorder=4,
        ))

        # Hatch overlay — separate patch keeps hatch linewidth independent
        old_lw = matplotlib.rcParams.get("hatch.linewidth", 1.0)
        matplotlib.rcParams["hatch.linewidth"] = 0.35
        ax.add_patch(PathPatch(
            combined,
            facecolor="none", hatch="////", edgecolor=pal["WALL_HATCH"],
            linewidth=0.0, zorder=5,
        ))
        matplotlib.rcParams["hatch.linewidth"] = old_lw

    # ── Layer 6 — void fills (white over hatch, one patch per hole) ──────────
    for hole_xy in loops[1:]:
        ax.add_patch(PathPatch(
            _simple_path(hole_xy),
            facecolor=pal["VOID_FILL"], edgecolor="none",
            zorder=6,
        ))

    # ── Layer 7 — service core fills ─────────────────────────────────────────
    cores = getattr(floor, "cores", None) or []
    for core in cores:
        ax.add_patch(mpatches.Rectangle(
            (core.x_min, core.y_min), core.width, core.depth,
            facecolor=pal["CORE_FILL"], edgecolor="none",
            zorder=7,
        ))

    # ── Layer 8 — column dots ─────────────────────────────────────────────────
    if column_grid is not None and loops:
        outer_path_obj = _simple_path(loops[0])
        dot_r = min(column_grid.span_x, column_grid.span_y) * 0.04
        for gx in column_grid.grid_lines_x:
            for gy in column_grid.grid_lines_y:
                inside = outer_path_obj.contains_point((gx, gy))
                alpha = 1.0 if inside else 0.30
                ax.add_patch(plt.Circle(
                    (gx, gy), dot_r,
                    color=pal["COLUMN_DOT"], alpha=alpha, zorder=8,
                ))

    # ── Layer 9 — outer building boundary (heaviest line) ────────────────────
    if loops:
        outer_closed = loops[0] + [loops[0][0]]
        xs, ys = zip(*outer_closed)
        ax.plot(
            xs, ys,
            color=pal["OUTER_EDGE"], linewidth=1.8,
            solid_capstyle="round", solid_joinstyle="round",
            zorder=9,
        )

    # ── Layer 10 — void / courtyard boundaries (medium line) ─────────────────
    for hole_xy in loops[1:]:
        closed = hole_xy + [hole_xy[0]]
        xs, ys = zip(*closed)
        ax.plot(
            xs, ys,
            color=pal["VOID_EDGE"], linewidth=1.0,
            solid_capstyle="round", solid_joinstyle="round",
            zorder=10,
        )

    # ── Layer 11 — core outlines (medium line) ───────────────────────────────
    for core in cores:
        ax.add_patch(mpatches.Rectangle(
            (core.x_min, core.y_min), core.width, core.depth,
            facecolor="none", edgecolor=pal["CORE_EDGE"], linewidth=1.2,
            zorder=11,
        ))

    # ── Layer 12 — column grid axis labels ───────────────────────────────────
    # Labels sit close to the building edge (at ~12 % of margin from the
    # building boundary), leaving the lower portion of the margin free for
    # the scale bar so they never overlap.
    if column_grid is not None and show_column_labels:
        num_label_offset = margin * 0.13   # column numbers below X axis
        alpha_label_offset = margin * 0.13  # row letters left of Y axis
        for i, gx in enumerate(column_grid.grid_lines_x):
            ax.text(
                gx, ymin_d - num_label_offset, str(i + 1),
                ha="center", va="top",
                fontsize=6.5, color=pal["GRID_LABEL"], zorder=12,
                clip_on=False,
            )
        for j, gy in enumerate(column_grid.grid_lines_y):
            label = chr(ord("A") + j) if j < 26 else f"A{j - 25}"
            ax.text(
                xmin_d - alpha_label_offset, gy, label,
                ha="right", va="center",
                fontsize=6.5, color=pal["GRID_LABEL"], zorder=12,
                clip_on=False,
            )

    # ── Layer 13 — scale bar ─────────────────────────────────────────────────
    # Anchored at ~45 % of margin from bottom — well below the building and
    # well above the figure edge, clear of the column axis labels above.
    if show_scale_bar:
        bar_anchor = (xlim[0] + margin * 0.25, ylim[0] + margin * 0.42)
        draw_scale_bar(ax, bar_anchor, pal)

    # ── Layer 14 — north arrow ────────────────────────────────────────────────
    if show_north_arrow:
        arrow_anchor = (xlim[1] - margin * 0.75, ylim[1] - margin * 1.6)
        draw_north_arrow(ax, arrow_anchor, pal)

    # ── Title ─────────────────────────────────────────────────────────────────
    if show_floor_label:
        ax.set_title(
            f"Floor {floor.index}   z = {floor.elevation:.1f} m",
            fontsize=9, pad=6, color="#2a3a4a",
        )


# ──────────────────────────────────────────────────────────────────────────────
# Multi-floor composition helper
# ──────────────────────────────────────────────────────────────────────────────

def draw_floor_plan_grid(
    floors: list,
    *,
    column_grid=None,
    original_footprint: list[tuple[float, float]] | None = None,
    n_cols: int = 3,
    subplot_size: float = 4.5,
    title: str | None = None,
    show_column_labels: bool = True,
    show_scale_bar: bool = True,
    show_north_arrow: bool = False,
    palette: dict | None = None,
    save_path: str | None = None,
    axes: "np.ndarray | None" = None,
) -> "matplotlib.figure.Figure":
    """
    Compose multiple floor plans into a single figure.

    Each floor gets one subplot.  ``draw_floor_plan`` is called once per floor
    with identical settings; the north arrow (if requested) is placed only in
    the first subplot to avoid clutter.

    Parameters
    ----------
    floors
        List of FloorData objects to plot.
    column_grid
        Forwarded to every ``draw_floor_plan`` call.
    original_footprint
        Forwarded to every ``draw_floor_plan`` call.
    n_cols
        Maximum number of columns in the subplot grid.
    subplot_size
        Size (inches) of each square subplot.
    title
        Figure-level suptitle (optional).
    show_column_labels, show_scale_bar, show_north_arrow
        Forwarded to ``draw_floor_plan``.  North arrow only on first subplot.
    palette
        Color overrides merged with DEFAULT_PALETTE.
    save_path
        If provided, the figure is saved to this path (dpi=150).
    axes
        Optional pre-created axes array (e.g. from ``plt.subplots``).
        If None a new figure is created.

    Returns
    -------
    matplotlib.figure.Figure
    """
    if not floors:
        raise ValueError("floors list is empty")

    pal = merge_palette(palette)
    num = len(floors)
    n_cols = min(n_cols, num)
    n_rows = math.ceil(num / n_cols)

    if axes is not None:
        fig = axes.flat[0].figure
        axes_flat = list(axes.flat)
    else:
        fig, ax_grid = plt.subplots(
            n_rows, n_cols,
            figsize=(n_cols * subplot_size, n_rows * subplot_size),
            squeeze=False,
            facecolor=pal["PAPER"],
        )
        axes_flat = list(ax_grid.flat)

    for idx, floor in enumerate(floors):
        draw_floor_plan(
            axes_flat[idx],
            floor,
            column_grid=column_grid,
            original_footprint=original_footprint,
            show_column_labels=show_column_labels,
            show_scale_bar=show_scale_bar,
            show_north_arrow=(show_north_arrow and idx == 0),
            show_floor_label=True,
            palette=palette,
        )

    # Hide unused subplots
    for idx in range(num, len(axes_flat)):
        axes_flat[idx].set_visible(False)

    # tight_layout first, then reserve top space for suptitle so the title
    # sits inside the figure rather than being clipped.
    fig.tight_layout()
    if title:
        fig.subplots_adjust(top=0.92)
        fig.suptitle(title, fontsize=12, y=0.97, color="#1a2a3a")

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig
