"""
Render an HTML page (384 CSS px = 384 dots), convert it to 1-bit, and print.

Defaults come from print_profile.DEFAULT_PROFILE (the settings picked on
paper); every flag below overrides one setting. --legacy starts from the
pre-2026-10 pipeline instead.

  --dither page   dither the whole screenshot (--method all prints every method)
  --dither photo  dither only the --photo at its exact on-page size, threshold the rest
  --dither none   threshold the whole screenshot

With --photo, the page needs one <img data-photo src="photo.png"> inside a
[data-photo-slot] block (see samples/photo-page/).

Examples:
  uv run src/scripts/page_print.py --page samples/ui-elements
  uv run src/scripts/page_print.py --page web/dist --legacy
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

from photo_dither import METHODS, PhotoError, dither, load, prepare  # noqa: E402
from print_profile import (  # noqa: E402
    AUTO_WEIGHT_MAX_BOLD_PX,
    DEFAULT_PROFILE,
    LEGACY_PROFILE,
    PrintProfile,
    capture_options,
    describe,
    erode,
    load_gray,
    threshold,
    to_bitmap,
)
from printer import PRINT_WIDTH_DOTS, open_printer  # noqa: E402
from raster_capture import capture_receipt  # noqa: E402

DEFAULT_PAGE = _PROJECT_ROOT / "samples" / "photo-page"
FONTS = _PROJECT_ROOT / "web" / "public" / "fonts"
SLOT_SELECTOR = "[data-photo-slot]"
PHOTO_SELECTOR = "img[data-photo]"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render an HTML page, convert it to 1-bit, print it.")
    parser.add_argument("--photo", type=Path, default=None, help="photo for the page's img[data-photo]")
    parser.add_argument(
        "--page",
        type=Path,
        default=DEFAULT_PAGE,
        help="directory with index.html (default: samples/photo-page)",
    )
    parser.add_argument("--legacy", action="store_true", help="start from the pre-2026-10 profile")
    parser.add_argument(
        "--dither",
        choices=("page", "photo", "none"),
        default=None,
        help="what gets dithered (default: page; none with --legacy)",
    )
    parser.add_argument(
        "--method",
        choices=(*METHODS, "all"),
        default=None,
        help=f"default: {DEFAULT_PROFILE.method}; 'all' only with --dither page",
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
        "--black-point",
        type=int,
        default=0,
        help="map black to this grey (0-254) so dark areas keep detail on paper (default: %(default)s)",
    )
    parser.add_argument(
        "--white-point",
        type=int,
        default=255,
        help="map white to this grey (1-255) so light skin keeps shading on paper (default: %(default)s)",
    )
    parser.add_argument(
        "--anti-aliased-text",
        dest="aliased_text",
        action="store_const",
        const=False,
        default=None,
        help="keep text anti-aliasing (default: aliased 1-bit glyphs)",
    )
    parser.add_argument("--font", default=None, help="override every font on the page, e.g. Verdana")
    parser.add_argument(
        "--font-file",
        type=Path,
        default=None,
        help="font file served to the page as the --font family (for fonts not installed)",
    )
    parser.add_argument(
        "--font-scale",
        type=float,
        default=None,
        help="multiply every font size; sizes are rounded to whole pixels (default: 1.0)",
    )
    parser.add_argument(
        "--weight",
        choices=("normal", "faux-bold", "bold", "auto"),
        default=None,
        help="faux-bold widens every stem by 1 dot; bold forces 700; "
        f"auto is bold below {AUTO_WEIGHT_MAX_BOLD_PX}px, regular above (default: auto)",
    )
    parser.add_argument(
        "--page-gamma",
        type=float,
        default=None,
        help="tone curve before --dither page; <1 darkens light greys (default: 1.0)",
    )
    parser.add_argument(
        "--no-halo",
        dest="light_text_halo",
        action="store_const",
        const=False,
        default=None,
        help="skip the black outline around light text",
    )
    parser.add_argument(
        "--no-erode",
        action="store_true",
        help="skip bottom-edge erosion (it offsets the print head's heat smear below strokes)",
    )
    parser.add_argument(
        "--erode-min-run",
        type=int,
        default=None,
        help=f"only trim vertical runs at least this tall (default: {DEFAULT_PROFILE.erode_min_run})",
    )
    parser.add_argument(
        "--no-label",
        action="store_true",
        help="skip the settings line printed above each page (for keepsakes, not tests)",
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
    if not 0 <= args.black_point < args.white_point <= 255:
        parser.error("need 0 <= --black-point < --white-point <= 255")
    if args.dither == "photo" and args.photo is None:
        parser.error("--dither photo needs --photo")
    if args.font_file and not args.font:
        parser.error("--font-file needs --font to name the family")
    if args.font_file and not args.font_file.is_file():
        parser.error(f"--font-file not found: {args.font_file}")
    for name in ("font_scale", "page_gamma"):
        value = getattr(args, name)
        if value is not None and not 0 < value < math.inf:
            parser.error(f"--{name.replace('_', '-')} must be a finite number greater than 0")
    if args.erode_min_run is not None and args.erode_min_run < 2:
        parser.error("--erode-min-run must be at least 2")
    if args.method == "all" and args.dither not in (None, "page"):
        parser.error("--method all only works with --dither page")
    return args


def profile_from_args(args: argparse.Namespace) -> PrintProfile:
    base = LEGACY_PROFILE if args.legacy else DEFAULT_PROFILE
    changes = {
        key: getattr(args, key)
        for key in ("aliased_text", "light_text_halo", "weight", "font", "font_file", "font_scale", "page_gamma")
        if getattr(args, key) is not None
    }
    if args.dither in ("page", "none"):
        changes["dither"] = args.dither
    if args.method not in (None, "all"):
        changes["method"] = args.method
    if args.erode_min_run is not None:
        changes["erode_min_run"] = args.erode_min_run
    if args.no_erode:
        changes["erode_min_run"] = None
    return base.with_(**changes)


def _build_site(page_dir: Path, site_dir: Path, font_file: Path | None) -> None:
    if not (page_dir / "index.html").is_file():
        sys.exit(f"ERROR: no index.html in {page_dir}")
    shutil.copytree(page_dir, site_dir, dirs_exist_ok=True)
    shutil.copytree(FONTS, site_dir / "fonts", dirs_exist_ok=True)
    if font_file:
        (site_dir / "fonts" / "override").mkdir(exist_ok=True)
        shutil.copy2(font_file, site_dir / "fonts" / "override" / font_file.name)


def _render(site_dir: Path, out_png: Path, selector: str, profile: PrintProfile) -> list[dict]:
    _, boxes = capture_receipt(
        site_dir,
        out_png=out_png,
        measure_selector=selector,
        snap_selector=PHOTO_SELECTOR,
        **capture_options(profile),
    )
    return boxes


def _one(boxes: list[dict], selector: str) -> dict:
    if len(boxes) != 1:
        sys.exit(f"ERROR: page must contain exactly one {selector}, found {len(boxes)}")
    return boxes[0]


def _slot_width(site_dir: Path, work_dir: Path, profile: PrintProfile) -> int:
    Image.new("L", (1, 1), 255).save(site_dir / "photo.png")
    box = _one(_render(site_dir, work_dir / "measure.png", SLOT_SELECTOR, profile), SLOT_SELECTOR)
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
    profile = profile_from_args(args)
    mode = args.dither or profile.dither
    photo = None
    if args.photo:
        try:
            photo = load(args.photo)
        except PhotoError as error:
            sys.exit(f"ERROR: {error}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_dir = (args.artifact_dir or _PROJECT_ROOT / "artifacts" / f"page-{stamp}").resolve()
    site_dir = artifact_dir / "site"
    _build_site(args.page.resolve(), site_dir, profile.font_file)

    gray = bitmap = None
    if photo is not None:
        gray = prepare(
            photo,
            width=_slot_width(site_dir, artifact_dir, profile),
            gamma=args.gamma,
            sharpen=args.sharpen,
            contrast_cutoff=args.contrast_cutoff,
            black_point=args.black_point,
            white_point=args.white_point,
        )
        bitmap = dither(gray, profile.method) if mode == "photo" else None
        (bitmap or gray).save(site_dir / "photo.png")

    shot_path = artifact_dir / "page.png"
    boxes = _render(site_dir, shot_path, PHOTO_SELECTOR, profile)
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

    page_gray = load_gray(shot_path)
    jobs: list[tuple[str | None, Image.Image]] = []
    if mode == "photo":
        out = threshold(page_gray)
        mismatches = mismatched_pixels(out, box, bitmap)
        print(f"Photo pixels changed by render + threshold: {mismatches} of {bitmap.width * bitmap.height}")
        if problems or mismatches:
            sys.exit("ERROR: photo is not pixel-exact on the page; not printing (see warnings above)")
        out = erode(out, profile)
        out.save(artifact_dir / f"photo-{profile.method}.png")
        label = describe(profile.with_(dither="none")).replace("threshold", f"photo {profile.method}", 1)
        jobs.append((label, out))
    elif profile.dither == "page":
        for method in METHODS if args.method == "all" else (profile.method,):
            out = to_bitmap(page_gray, profile, method=method)
            out.save(artifact_dir / f"page-{method}.png")
            jobs.append((describe(profile.with_(method=method)), out))
    else:
        out = to_bitmap(page_gray, profile)
        out.save(artifact_dir / "threshold.png")
        jobs.append((describe(profile), out))

    if args.no_print:
        print(f"Artifacts: {artifact_dir}")
        return
    if photo is not None:
        tone = f"photo gamma {args.gamma}, range {args.black_point}-{args.white_point}, cutoff {args.contrast_cutoff}"
        jobs = [(f"{label}; {tone}", image) for label, image in jobs]
    _print([(None if args.no_label else label, image) for label, image in jobs])
    print(f"Printed {len(jobs)} page(s). Artifacts: {artifact_dir}")


if __name__ == "__main__":
    main()
