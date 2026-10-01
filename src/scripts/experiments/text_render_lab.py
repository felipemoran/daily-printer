"""
Render a receipt page under text-rendering variants and write a zoomed comparison sheet.

Variants: default anti-aliasing, --disable-font-subpixel-positioning,
-webkit-font-smoothing: none, and a 2x supersample; each thresholded at 200
(the legacy receipt) and 128. Screen-only: it shows what each variant hands
to the threshold, not dot gain on paper.

Example:
  uv run src/scripts/experiments/text_render_lab.py --page web/dist --crop 150,330
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from printer import PRINT_WIDTH_DOTS  # noqa: E402
from raster_capture import static_server  # noqa: E402

# Forced explicitly: the receipt app turns smoothing off itself since 2026-10.
_AA = "* { -webkit-font-smoothing: antialiased !important; }"
VARIANTS = [  # name, chromium args, injected css, device scale factor
    ("default", [], _AA, 1),
    ("no-subpixel-pos", ["--disable-font-subpixel-positioning"], _AA, 1),
    ("smoothing-none", [], "* { -webkit-font-smoothing: none !important; }", 1),
    ("2x", [], _AA, 2),
]


def _render(port: int, args: list[str], css: str, scale: int, tmp: Path) -> Image.Image:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=args)
        page = browser.new_page(device_scale_factor=scale, viewport={"width": PRINT_WIDTH_DOTS, "height": 720})
        page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="networkidle")
        if css:
            page.add_style_tag(content=css)
        page.locator("#receipt").screenshot(path=str(tmp))
        browser.close()
    image = Image.open(tmp).convert("L")
    if scale != 1:
        image = image.resize((PRINT_WIDTH_DOTS, round(image.height / scale)), Image.Resampling.BOX)
    return image


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--page", type=Path, default=_PROJECT_ROOT / "web" / "dist", help="folder with index.html")
    parser.add_argument("--crop", default="150,330", help="top,bottom rows to compare")
    parser.add_argument("--out", type=Path, default=_PROJECT_ROOT / "artifacts" / "text-render-lab.png")
    args = parser.parse_args()
    top, bottom = map(int, args.crop.split(","))
    args.out.parent.mkdir(parents=True, exist_ok=True)

    with static_server(args.page) as port:
        renders = {name: _render(port, a, c, s, args.out.with_suffix(".tmp.png")) for name, a, c, s in VARIANTS}
    args.out.with_suffix(".tmp.png").unlink(missing_ok=True)

    panels = []
    for name, image in renders.items():
        levels = len(set(image.crop((0, 0, PRINT_WIDTH_DOTS, min(400, image.height))).tobytes()))
        print(f"{name:16} grey levels in the top 400 rows: {levels}")
        crop = image.crop((0, top, PRINT_WIDTH_DOTS, bottom))
        for limit in (200, 128):
            panels.append((f"{name} threshold {limit}", crop.point(lambda v, t=limit: 255 if v > t else 0)))
    zoom, w, h = 2, PRINT_WIDTH_DOTS * 2, (bottom - top) * 2
    sheet = Image.new("L", (w * 2 + 30, (h + 22) * (len(panels) // 2)), 200)
    draw = ImageDraw.Draw(sheet)
    for index, (label, image) in enumerate(panels):
        x, y = (index % 2) * (w + 30), (index // 2) * (h + 22)
        draw.text((x + 4, y + 4), label, fill=0)
        sheet.paste(image.resize((w, h), Image.Resampling.NEAREST), (x, y + 20))
    sheet.save(args.out)
    print(f"Sheet: {args.out}")


if __name__ == "__main__":
    main()
