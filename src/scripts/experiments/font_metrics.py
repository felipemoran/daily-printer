"""
Measure fonts the way they print: aliased stem width, characters per 384-dot line, x-height.

Stem width is the median black run across a row of 'l' and 'I' glyphs rendered
with -webkit-font-smoothing: none. 2-dot stems matched the printer's Font A
best in 2026-10 tests; see docs/research-print-quality.md.

Example:
  uv run src/scripts/experiments/font_metrics.py --fonts "Tahoma:400,700" "Verdana:400,700" --sizes 16,19,22
"""

from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from printer import PRINT_WIDTH_DOTS  # noqa: E402
from raster_capture import static_server  # noqa: E402

SAMPLE = "Buy milk and call the dentist before Friday at 10:30"
DEFAULT_FONTS = ["Verdana:400,700", "Tahoma:400,700", "Avenir Next Condensed:500,600,700"]
_WIDTH_JS = """([family, weight, sample]) => {
  const c = document.createElement('canvas').getContext('2d');
  c.font = `${weight} 16px '${family}'`;
  return [c.measureText(sample).width / sample.length / 16, c.measureText('x').actualBoundingBoxAscent / 16,
          document.fonts.check(`${weight} 16px '${family}'`)];
}"""


def stem_width(image: Image.Image, y: int) -> float:
    """Median width of the black runs along row ``y`` (0 when the row is blank)."""
    runs, run = [], 0
    for x in range(image.width):
        if image.getpixel((x, y)) < 128:
            run += 1
        elif run:
            runs.append(run)
            run = 0
    if run:
        runs.append(run)
    return statistics.median(runs) if runs else 0


def _parse_fonts(specs: list[str]) -> list[tuple[str, int]]:
    out = []
    for spec in specs:
        family, _, weights = spec.partition(":")
        out += [(family, int(w)) for w in (weights or "400").split(",")]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--fonts", nargs="+", default=DEFAULT_FONTS, help='"Family:w1,w2" (installed fonts)')
    parser.add_argument("--sizes", default="16,19,22", help="comma-separated px sizes")
    args = parser.parse_args()
    combos = [(f, s, w) for f, w in _parse_fonts(args.fonts) for s in map(int, args.sizes.split(","))]

    with tempfile.TemporaryDirectory() as tmp:
        site = Path(tmp)
        rows = "".join(f'<div style="font:{w} {s}px/{s * 2}px \'{f}\'">llllllll IIIIIIII</div>' for f, s, w in combos)
        (site / "index.html").write_text(
            "<style>*{-webkit-font-smoothing:none}body{margin:0}</style>"
            f'<main id="receipt" style="width:{PRINT_WIDTH_DOTS}px">{rows}</main>'
        )
        with static_server(site) as port, sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": PRINT_WIDTH_DOTS, "height": 2000})
            page.goto(f"http://127.0.0.1:{port}/index.html")
            boxes = page.evaluate("() => [...document.querySelectorAll('#receipt > div')].map(d => [d.offsetTop, d.offsetHeight])")
            page.locator("#receipt").screenshot(path=str(site / "shot.png"))
            widths = {(f, w): page.evaluate(_WIDTH_JS, [f, w, SAMPLE]) for f, _, w in combos}
            browser.close()
        shot = Image.open(site / "shot.png").convert("L")

    print(f"{'font':26}{'size':>5}{'weight':>7}{'stem dots':>10}{'chars/line':>11}{'x-height':>9}  loaded")
    for (family, size, weight), (top, height) in zip(combos, boxes):
        per_char_em, x_em, loaded = widths[(family, weight)]
        print(
            f"{family:26}{size:>5}{weight:>7}{stem_width(shot, top + height // 2):>10}"
            f"{PRINT_WIDTH_DOTS / (per_char_em * size):>11.1f}{x_em * size:>9.1f}  {'yes' if loaded else 'NO (fallback)'}"
        )


if __name__ == "__main__":
    main()
