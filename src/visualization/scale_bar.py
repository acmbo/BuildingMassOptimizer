"""
Scale bar and north arrow helpers for architectural floor plan plots.

All coordinates are in data units (model metres) so the annotations scale
correctly when the axes are zoomed or resized.
"""

import matplotlib.patches as mpatches


def draw_scale_bar(
    ax,
    anchor_xy: tuple[float, float],
    palette: dict[str, str],
    bar_length_m: float = 5.0,
    segment_count: int = 5,
) -> None:
    """
    Draw a segmented scale bar at *anchor_xy* (data coordinates).

    The bar is ``bar_length_m`` metres long divided into ``segment_count``
    alternating black / white 1-metre segments.  Labels "0" and "5 m" are
    placed below the bar ends; a small "1:200" notation appears centred below.

    Parameters
    ----------
    ax            : matplotlib Axes
    anchor_xy     : (x, y) lower-left corner of the bar in data units
    palette       : colour dict — uses key "SCALE_BAR"
    bar_length_m  : total bar length in metres
    segment_count : number of alternating segments
    """
    x0, y0 = anchor_xy
    seg_len = bar_length_m / segment_count
    bar_h   = seg_len * 0.28          # bar height in data units

    color = palette["SCALE_BAR"]

    for i in range(segment_count):
        fc = color if i % 2 == 0 else "white"
        ax.add_patch(mpatches.Rectangle(
            (x0 + i * seg_len, y0), seg_len, bar_h,
            facecolor=fc, edgecolor=color, linewidth=0.7,
            zorder=20, clip_on=False,
        ))

    # End labels
    label_y = y0 - bar_h * 0.45
    for x_lbl, text, ha in [
        (x0,                 "0",              "center"),
        (x0 + bar_length_m,  f"{bar_length_m:.0f} m", "center"),
    ]:
        ax.text(
            x_lbl, label_y, text,
            ha=ha, va="top", fontsize=6.0, color=color, zorder=20,
            clip_on=False,
        )

    # Scale notation
    ax.text(
        x0 + bar_length_m / 2, label_y - bar_h * 1.4, "1:200",
        ha="center", va="top", fontsize=5.5, color=color, zorder=20,
        clip_on=False,
    )


def draw_north_arrow(
    ax,
    anchor_xy: tuple[float, float],
    palette: dict[str, str],
    arrow_len: float = 1.5,
) -> None:
    """
    Draw a simple north arrow (↑ N) at *anchor_xy* (data coordinates).

    Parameters
    ----------
    ax         : matplotlib Axes
    anchor_xy  : (x, y) base of the arrow shaft in data units
    palette    : colour dict — uses key "SCALE_BAR"
    arrow_len  : length of the arrow shaft in data units
    """
    x, y = anchor_xy
    color = palette["SCALE_BAR"]

    ax.annotate(
        "",
        xy=(x, y + arrow_len),
        xytext=(x, y),
        arrowprops=dict(
            arrowstyle="-|>",
            color=color,
            lw=1.2,
            mutation_scale=10,
        ),
        zorder=20,
        annotation_clip=False,
    )
    ax.text(
        x, y + arrow_len + arrow_len * 0.22, "N",
        ha="center", va="bottom",
        fontsize=7.5, fontweight="bold",
        color=color, zorder=20,
        clip_on=False,
    )
