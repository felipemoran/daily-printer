"""
setup_test.py — Phase 1: minimal printer test.

Prints a title and a width-calibration strip.

Run:
    uv run src/setup_test.py
"""

from PIL import Image, ImageDraw
from printer import open_printer, PRINT_WIDTH_DOTS

# Widths to probe, centered around the expected value.
PROBE_WIDTHS = [320, 352, 368, 374, 376, 378, 380, 382, 384, 386, 388, 390, 392, 400, 416]


def make_calibration_strip(canvas_width: int = max(PROBE_WIDTHS)) -> Image.Image:
    """
    Single image with one bar per probe width.
    Each bar is drawn left-to-right; the label is baked in on the left
    in white-on-black so it remains visible even if the bar is clipped.

    The bar that visually reaches the paper edge (no gap, no overflow)
    is the true printable width.
    """
    row_h = 14
    gap = 3
    height = len(PROBE_WIDTHS) * (row_h + gap) - gap

    img = Image.new("1", (canvas_width, height), 1)  # white background
    draw = ImageDraw.Draw(img)

    for i, w in enumerate(PROBE_WIDTHS):
        y = i * (row_h + gap)
        bar_w = w  # intentionally allow wider than expected to observe printer behaviour
        draw.rectangle([0, y, bar_w - 1, y + row_h - 1], fill=0)          # black bar
        draw.text((2, y + 3), str(w), fill=1)                              # white label

    return img


def run():
    p = open_printer()

    p.set(align="left", bold=True)
    p.text("Width calibration\n")
    p.set(bold=False)

    img = make_calibration_strip()
    # Temporarily raise the profile cap so the library sends the full canvas.
    p.profile.profile_data["media"]["width"]["pixels"] = img.width
    p.image(img, impl="bitImageRaster")
    p.ln(2)


if __name__ == "__main__":
    run()
