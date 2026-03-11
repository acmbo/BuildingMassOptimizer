"""
Visualize an .hbjson file exported by this project as a self-contained HTML file.

Uses honeybee-display + ladybug-vtk to produce a standalone .html file that can
be opened in any browser — no server required.

Usage:
    python scripts/visualize_hbjson.py <path/to/model.hbjson> [output.html]

    If output path is omitted the HTML is written next to the input file.

Example:
    conda run -n pyoccEnvRadianceTest python scripts/visualize_hbjson.py /tmp/test_building.hbjson
"""
import sys
import os

try:
    from honeybee_display.cli import model_to_vis_set
except ImportError as exc:
    sys.exit(
        f"Missing dependency: {exc}\n"
        "Run: pip install honeybee-display ladybug-vtk"
    )


def main(hbjson_path: str, output_html: str | None = None) -> None:
    if not os.path.isfile(hbjson_path):
        sys.exit(f"File not found: {hbjson_path}")

    if output_html is None:
        base = os.path.splitext(hbjson_path)[0]
        output_html = base + ".html"

    print(f"Loading {hbjson_path} ...")
    print(f"Writing HTML to {output_html} ...")

    model_to_vis_set(
        model_file=hbjson_path,
        output_format="html",
        output_file=output_html,
    )

    print(f"\nDone. Open this file in your browser:")
    print(f"  {output_html}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(f"Usage: python {sys.argv[0]} <model.hbjson> [output.html]")
    html_out = sys.argv[2] if len(sys.argv) >= 3 else None
    main(sys.argv[1], html_out)
