"""
Print a photo on the thermal printer, dithered for 384-dot paper.

Examples:
  uv run src/scripts/photo_print.py me.jpg --compare          # screen sheet of every method
  uv run src/scripts/photo_print.py me.jpg --test-strip       # paper strip of every method
  uv run src/scripts/photo_print.py me.jpg --method atkinson --gamma 1.5
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from photo_dither import METHODS, dither, prepare  # noqa: E402
from printer import PRINT_WIDTH_DOTS, open_printer  # noqa: E402

STRIP_BAND_PX = 128  # 16 mm of paper per method
TALL_WARNING_PX = 2400  # 30 cm of paper
SHEET_SCALE = 2  # nearest-neighbour upscale so dots are visible on screen
SHEET_COLUMNS = 3


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dither a photo for the thermal printer and print it.",
        epilog="Prints come out darker than the preview (dots bleed). "
        "Raise --gamma if faces look muddy on paper.",
    )
    parser.add_argument("photo", type=Path, help="JPEG/PNG/WebP/AVIF file")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--compare",
        action="store_true",
        help="write a sheet with every method side by side; never prints",
    )
    mode.add_argument(
        "--test-strip",
        action="store_true",
        help=f"print a {STRIP_BAND_PX}px band of the photo per method, to judge on real paper",
    )
    parser.add_argument(
        "--method",
        choices=METHODS,
        default="atkinson",
        help="default: %(default)s; ignored with --compare and --test-strip",
    )
    parser.add_argument(
        "--gamma",
        type=float,
        default=1.3,
        help="midtone lift; >1 lightens to offset dot gain (default: %(default)s)",
    )
    parser.add_argument(
        "--sharpen",
        type=int,
        default=100,
        help="unsharp-mask percent, 0 to disable (default: %(default)s)",
    )
    parser.add_argument(
        "--contrast-cutoff",
        type=float,
        default=1.0,
        help="percent of darkest/lightest pixels clipped by autocontrast, 0 to disable (default: %(default)s)",
    )
    parser.add_argument("--no-print", action="store_true", help="only write preview PNGs")
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="where previews go (default: artifacts/photo-<utc-timestamp>)",
    )
    args = parser.parse_args()
    if not 0 < args.gamma < math.inf:
        parser.error("--gamma must be a finite number greater than 0")
    return args


def _load(path: Path) -> Image.Image:
    if not path.is_file():
        sys.exit(f"ERROR: photo not found: {path}")
    try:
        image = Image.open(path)
        image.load()
        return image
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        hint = f"\n  {error}"
        if path.suffix.lower() in (".heic", ".heif"):
            hint += f"\n  Pillow cannot read HEIC. Convert it first:\n  sips -s format jpeg '{path}' --out '{path.with_suffix('.jpg')}'"
        sys.exit(f"ERROR: not a readable image: {path}{hint}")


def _font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    try:
        return ImageFont.load_default(size=size)
    except (TypeError, OSError):
        return ImageFont.load_default()


def _labelled(panel: Image.Image, label: str) -> Image.Image:
    label_height = 36
    out = Image.new("L", (panel.width, panel.height + label_height), 255)
    out.paste(panel.convert("L"), (0, label_height))
    ImageDraw.Draw(out).text((8, 6), label, fill=0, font=_font(22))
    return out


def _compare_sheet(gray: Image.Image, settings: str) -> Image.Image:
    panels = []
    for method in METHODS:
        bitmap = dither(gray, method)
        scaled = bitmap.resize((bitmap.width * SHEET_SCALE, bitmap.height * SHEET_SCALE), Image.Resampling.NEAREST)
        panels.append(_labelled(scaled, method))

    gutter = 16
    rows = -(-len(panels) // SHEET_COLUMNS)
    cell_w, cell_h = panels[0].size
    header = 40
    sheet = Image.new(
        "L",
        (SHEET_COLUMNS * cell_w + (SHEET_COLUMNS + 1) * gutter, header + rows * cell_h + (rows + 1) * gutter),
        235,
    )
    ImageDraw.Draw(sheet).text((gutter, 10), settings, fill=0, font=_font(20))
    for index, panel in enumerate(panels):
        column, row = index % SHEET_COLUMNS, index // SHEET_COLUMNS
        sheet.paste(panel, (gutter + column * (cell_w + gutter), header + gutter + row * (cell_h + gutter)))
    return sheet


def _band(bitmap: Image.Image) -> Image.Image:
    height = min(STRIP_BAND_PX, bitmap.height)
    # Faces in portraits tend to sit above centre.
    top = max(0, min(bitmap.height - height, round(bitmap.height * 0.35) - height // 2))
    return bitmap.crop((0, top, bitmap.width, top + height))


def _print(send) -> None:
    try:
        with open_printer() as p:
            send(p)
            p.ln(3)
    except SystemExit:
        raise
    except Exception as error:
        sys.exit(f"ERROR: print failed: {error}")


def main() -> None:
    args = _parse_args()
    gray = prepare(
        _load(args.photo),
        width=PRINT_WIDTH_DOTS,
        gamma=args.gamma,
        sharpen=args.sharpen,
        contrast_cutoff=args.contrast_cutoff,
    )
    settings = f"gamma={args.gamma}  sharpen={args.sharpen}  cutoff={args.contrast_cutoff}"

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_dir = (args.artifact_dir or _PROJECT_ROOT / "artifacts" / f"photo-{stamp}").resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stem = args.photo.stem

    if args.compare:
        sheet_path = artifact_dir / f"{stem}-compare.png"
        _compare_sheet(gray, settings).save(sheet_path)
        print(f"Compare sheet: {sheet_path}")
        return

    if args.test_strip:
        bands = {method: _band(dither(gray, method)) for method in METHODS}
        for method, band in bands.items():
            band.save(artifact_dir / f"{stem}-strip-{method}.png")
        if args.no_print:
            print(f"Strip previews: {artifact_dir}")
            return

        def send_strip(p) -> None:
            p.text(f"{stem}\n{settings}\n")
            for method, band in bands.items():
                p.text(f"\n{method}\n")
                p.image(band, center=False)

        _print(send_strip)
        print(f"Printed test strip ({len(bands)} methods). Previews: {artifact_dir}")
        return

    bitmap = dither(gray, args.method)
    if bitmap.height > TALL_WARNING_PX:
        print(
            f"WARNING: {bitmap.height} dots is about {bitmap.height // 80} cm of paper.",
            file=sys.stderr,
        )
    preview_path = artifact_dir / f"{stem}-{args.method}.png"
    bitmap.save(preview_path)
    if args.no_print:
        print(f"Preview: {preview_path}")
        return
    _print(lambda p: p.image(bitmap, center=False))
    print(f"Printed {bitmap.width}x{bitmap.height} ({args.method}). Preview: {preview_path}")


if __name__ == "__main__":
    main()
