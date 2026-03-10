"""
Colour palette for architectural floor plan visualizations.

All values are hex strings.  Override individual tokens by passing a dict to
any draw_* function — unrecognized keys are silently ignored.
"""

DEFAULT_PALETTE: dict[str, str] = {
    # Backgrounds
    "PAPER":          "#fafaf7",   # axes + figure background (off-white paper)

    # Floor solid material
    "FLOOR_FILL":     "#e8ecf0",   # solid floor area (light cool grey)
    "WALL_HATCH":     "#9aa8b8",   # 45° hatch lines over floor fill

    # Voids — courtyards, atriums, subtracted areas
    "VOID_FILL":      "#ffffff",   # interior void fill (white)
    "VOID_EDGE":      "#4a6080",   # courtyard boundary line (medium weight)

    # Building perimeter
    "OUTER_EDGE":     "#1a2a3a",   # outer building boundary (heavy weight)

    # Original (un-subtracted) footprint reference
    "ORIG_FOOTPRINT": "#cc8866",   # dashed reference outline

    # Column grid
    "GRID_LINE":      "#b0bcc8",   # column grid lines (light dash-dot)
    "GRID_LABEL":     "#6a7a8a",   # axis labels beside grid lines
    "COLUMN_DOT":     "#2a3a4a",   # filled circle at column intersections

    # Service cores
    "CORE_FILL":      "#c0d4f0",   # core footprint fill (light blue)
    "CORE_EDGE":      "#1a3a80",   # core boundary line

    # Annotations
    "SCALE_BAR":      "#1a2a3a",   # scale bar, north arrow, dimension text
}


def merge_palette(overrides: dict | None) -> dict[str, str]:
    """Return a copy of DEFAULT_PALETTE updated with any overrides."""
    if not overrides:
        return dict(DEFAULT_PALETTE)
    return {**DEFAULT_PALETTE, **overrides}
