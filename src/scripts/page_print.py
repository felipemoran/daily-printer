"""
Render an HTML page (384 CSS px = 384 dots), dither, and print.

  --dither page   dither the whole screenshot (--method all prints every method)
  --dither photo  dither only the --photo at its exact on-page size, threshold the rest
  --dither none   threshold the whole screenshot, as receipt_print does

With --photo, the page needs one <img data-photo src="photo.png"> inside a
[data-photo-slot] block (see samples/photo-page/).

Examples:
  uv run src/scripts/page_print.py --page samples/ui-elements --dither none
  uv run src/scripts/page_print.py --photo data/me.jpg --dither photo
"""

from __future__ import annotations

import argparse
import math
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageChops

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from photo_dither import METHODS, PhotoError, dither, erode_bottom_edges, load, prepare  # noqa: E402
from printer import PRINT_WIDTH_DOTS, open_printer  # noqa: E402
from raster_capture import capture_receipt  # noqa: E402
from receipt_image import prepare_for_escpos  # noqa: E402

DEFAULT_PAGE = _PROJECT_ROOT / "samples" / "photo-page"
FONTS = _PROJECT_ROOT / "web" / "public" / "fonts"
SLOT_SELECTOR = "[data-photo-slot]"
PHOTO_SELECTOR = "img[data-photo]"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render an HTML page, dither it, print it.")
    parser.add_argument("--photo", type=Path, default=None, help="photo for the page's img[data-photo]")
    parser.add_argument(
        "--page",
        type=Path,
        default=DEFAULT_PAGE,
        help="directory with index.html (default: samples/photo-page)",
    )
    parser.add_argument(
        "--dither",
        choices=("page", "photo", "none"),
        default="page",
        help="what gets dithered (default: %(default)s)",
    )
    parser.add_argument(
        "--method",
        choices=(*METHODS, "all"),
        default="atkinson",
        help="default: %(default)s; 'all' only with --dither page",
    )
    parser.add_argument("--gamma", type=float, default=1.3, help="photo midtone lift (default: %(default)s)")
    parser.add_argument("--sharpen", type=int, default=100, help="photo unsharp-mask percent (default: %(default)s)")
    parser.add_argument(
        "--contrast-cutoff",
        type=float,
        default=1.0,
        help="photo autocontrast clip percent (default: %(default)s)",
    )
    parser.add_argument(
        "--aliased-text",
        action="store_true",
        help="render text without anti-aliasing (crisp 1-bit glyphs)",
    )
    parser.add_argument(
        "--font",
        default=None,
        help="override every font on the page, e.g. Verdana",
    )
    parser.add_argument(
        "--no-erode",
        action="store_true",
        help="skip bottom-edge erosion (it offsets the print head's heat smear below strokes)",
    )
    parser.add_argument(
        "--erode-min-run",
        type=int,
        default=3,
        help="only trim vertical runs at least this tall; 3 spares dither textures (default: %(default)s)",
    )
    parser.add_argument("--no-print", action="store_true", help="only write PNGs")
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="default: artifacts/page-<utc-timestamp>",
    )
    args = parser.parse_args()
    if not 0 < args.gamma < math.inf:
        parser.error("--gamma must be a finite number greater than 0")
    if args.dither == "photo" and args.photo is None:
        parser.error("--dither photo needs --photo")
    if args.erode_min_run < 2:
        parser.error("--erode-min-run must be at least 2")
    if args.method == "all" and args.dither != "page":
        parser.error("--method all only works with --dither page")
    return args


def _build_site(page_dir: Path, site_dir: Path) -> None:
    if not (page_dir / "index.html").is_file():
        sys.exit(f"ERROR: no index.html in {page_dir}")
    shutil.copytree(page_dir, site_dir, dirs_exist_ok=True)
    shutil.copytree(FONTS, site_dir / "fonts", dirs_exist_ok=True)


def _render(site_dir: Path, out_png: Path, selector: str, aliased_text: bool, font: str | None) -> list[dict]:
    _, boxes = capture_receipt(
        site_dir,
        out_png=out_png,
        measure_selector=selector,
        snap_selector=PHOTO_SELECTOR,
        aliased_text=aliased_text,
        extra_css=f"#receipt, #receipt * {{ font-family: '{font}' !important; }}" if font else None,
    )
    return boxes


def _one(boxes: list[dict], selector: str) -> dict:
    if len(boxes) != 1:
        sys.exit(f"ERROR: page must contain exactly one {selector}, found {len(boxes)}")
    return boxes[0]


def _slot_width(site_dir: Path, work_dir: Path, font: str | None) -> int:
    Image.new("L", (1, 1), 255).save(site_dir / "photo.png")
    box = _one(_render(site_dir, work_dir / "measure.png", SLOT_SELECTOR, False, font), SLOT_SELECTOR)
    if box["width"] != int(box["width"]):
        sys.exit(f"ERROR: {SLOT_SELECTOR} is {box['width']}px wide; make it a whole number of pixels")
    return int(box["width"])


def alignment_problems(page_width: int, box: dict, photo_size: tuple[int, int]) -> list[str]:
    """Reasons the photo will not land on printer dots 1:1 (empty when it will)."""
    problems = []
    if page_width != PRINT_WIDTH_DOTS:
        problems.append(f"page renders {page_width}px wide, printer is {PRINT_WIDTH_DOTS} dots")
    for key in ("x", "y", "width", "height"):
        if box[key] != int(box[key]):
            problems.append(f"photo {key}={box[key]} is not a whole pixel")
    if (box["width"], box["height"]) != photo_size:
        problems.append(
            f"photo renders at {box['width']}x{box['height']}, file is {photo_size[0]}x{photo_size[1]} (browser is scaling it)"
        )
    return problems


def mismatched_pixels(page: Image.Image, box: dict, bitmap: Image.Image) -> int:
    x, y = int(box["x"]), int(box["y"])
    region = page.crop((x, y, x + bitmap.width, y + bitmap.height)).convert("L")
    difference = ImageChops.difference(region, bitmap.convert("L"))
    return bitmap.width * bitmap.height - difference.histogram()[0]


def _print(jobs: list[tuple[str | None, Image.Image]]) -> None:
    try:
        with open_printer() as p:
            for label, image in jobs:
                if label:
                    p.text(f"{label}\n")
                p.image(image, center=False)
                p.ln(2)
            p.ln(1)
    except SystemExit:
        raise
    except Exception as error:
        sys.exit(f"ERROR: print failed: {error}")


def main() -> None:
    args = _parse_args()
    photo = None
    if args.photo:
        try:
            photo = load(args.photo)
        except PhotoError as error:
            sys.exit(f"ERROR: {error}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_dir = (args.artifact_dir or _PROJECT_ROOT / "artifacts" / f"page-{stamp}").resolve()
    site_dir = artifact_dir / "site"
    _build_site(args.page.resolve(), site_dir)

    gray = bitmap = None
    if photo is not None:
        gray = prepare(
            photo,
            width=_slot_width(site_dir, artifact_dir, args.font),
            gamma=args.gamma,
            sharpen=args.sharpen,
            contrast_cutoff=args.contrast_cutoff,
        )
        bitmap = dither(gray, args.method) if args.dither == "photo" else None
        (bitmap or gray).save(site_dir / "photo.png")

    shot_path = artifact_dir / "page.png"
    boxes = _render(site_dir, shot_path, PHOTO_SELECTOR, args.aliased_text, args.font)
    shot = Image.open(shot_path)
    print(f"Rendered {shot.width}x{shot.height} px")
    problems = [] if shot.width == PRINT_WIDTH_DOTS else [f"page renders {shot.width}px wide, printer is {PRINT_WIDTH_DOTS} dots"]
    box = None
    if gray is not None:
        box = _one(boxes, PHOTO_SELECTOR)
        problems = alignment_problems(shot.width, box, gray.size)
        print(f"Photo slot {gray.width}x{gray.height} at ({box['x']}, {box['y']})")
    for problem in problems:
        print(f"WARNING: {problem}", file=sys.stderr)

    text = ", ".join([
        args.font or "page fonts",
        "aliased" if args.aliased_text else "anti-aliased",
        "no erosion" if args.no_erode else f"erosion run>={args.erode_min_run}",
    ])
    jobs: list[tuple[str | None, Image.Image]] = []
    if args.dither == "page":
        page_gray = shot.convert("L")
        for method in METHODS if args.method == "all" else (args.method,):
            out = dither(page_gray, method)
            if not args.no_erode:
                out = erode_bottom_edges(out, min_run=args.erode_min_run)
            out.save(artifact_dir / f"page-{method}.png")
            jobs.append((f"dither: page / {method}, {text}", out))
    else:
        out = prepare_for_escpos(shot_path, target_width=PRINT_WIDTH_DOTS, dither=False)
        if args.dither == "photo":
            out.save(artifact_dir / f"photo-{args.method}.png")
            mismatches = mismatched_pixels(out, box, bitmap)
            print(f"Photo pixels changed by render + threshold: {mismatches} of {bitmap.width * bitmap.height}")
            if problems or mismatches:
                sys.exit("ERROR: photo is not pixel-exact on the page; not printing (see warnings above)")
            if not args.no_erode:
                out = erode_bottom_edges(out, min_run=args.erode_min_run)
                out.save(artifact_dir / f"photo-{args.method}.png")
            jobs.append((f"dither: photo / {args.method}, {text}", out))
        else:
            if not args.no_erode:
                out = erode_bottom_edges(out, min_run=args.erode_min_run)
            out.save(artifact_dir / "threshold.png")
            jobs.append((f"dither: none (threshold), {text}", out))

    if args.no_print:
        print(f"Artifacts: {artifact_dir}")
        return
    _print(jobs)
    print(f"Printed {len(jobs)} page(s). Artifacts: {artifact_dir}")


if __name__ == "__main__":
    main()
