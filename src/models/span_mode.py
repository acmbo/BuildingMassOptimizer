from enum import Enum


class SpanMode(Enum):
    """Determines how the column grid span size is resolved."""

    FIXED_SPAN = "fixed_span"
    """User provides absolute span lengths (span_x, span_y) in model units.
    The number of spans is derived by dividing the polygon bounding box with ceil."""

    SPAN_COUNT = "span_count"
    """User provides the number of spans (nx_spans, ny_spans).
    The span lengths are derived by dividing the polygon bounding box evenly."""
