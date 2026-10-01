"""
Print one photo slice per value of a tone setting, side by side, for paper A/B rounds.

Each column is the same slice of the photo at final print scale, so dot gain
on paper is judged at the size it will really print. Values are drawn above
each column. Binary-search a setting: wide values first, then narrow around
the pick.

Example (round 1 of the 2026-10 shadow search):
  uv run src/scripts/experiments/tone_sweep.py data/me.jpg \\
      --param black-point --values 32,64,96 --white-point 245 --slice-left 256
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from photo_dither import METHODS, PhotoError, dither, erode_bottom_edges, load, prepare  # noqa: E402
from printer import PRINT_WIDTH_DOTS, open_printer  # noqa: E402

PARAMS = ("black-point", "white-point", "gamma", "contrast-cutoff", "sharpen")
LABEL_PX = 18


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("photo", type=Path)
    parser.add_argument("--param", choices=PARAMS, required=True, help="setting to vary across columns")
    parser.add_argument("--values", required=True, help="comma-separated values, one column each")
    parser.add_argument("--slice-left", type=int, default=0, help="left edge of the slice, in print dots")
    parser.add_argument("--gamma", type=float, default=1.0)
    parser.add_argument("--contrast-cutoff", type=float, default=0.0)
    parser.add_argument("--sharpen", type=int, default=100)
    parser.add_argument("--black-point", type=int, default=0)
    parser.add_argument("--white-point", type=int, default=255)
    parser.add_argument("--method", choices=METHODS, default="atkinson")
    parser.add_argument("--erode-min-run", type=int, default=3, help="0 disables erosion (default: %(default)s)")
    parser.add_argument("--no-print", action="store_true")
    parser.add_argument("--out", type=Path, default=_PROJECT_ROOT / "artifacts" / "tone-sweep.png")
    args = parser.parse_args()
    if not [value for value in args.values.split(",") if value.strip()]:
        parser.error("--values needs at least one value")
    if args.erode_min_run == 1 or args.erode_min_run < 0:
        parser.error("--erode-min-run must be 0 (off) or at least 2")
    return args


def _settings(args: argparse.Namespace, value: str) -> dict:
    settings = {
        "gamma": args.gamma,
        "contrast_cutoff": args.contrast_cutoff,
        "sharpen": args.sharpen,
        "black_point": args.black_point,
        "white_point": args.white_point,
    }
    key = args.param.replace("-", "_")
    settings[key] = float(value) if key in ("gamma", "contrast_cutoff") else int(value)
    return settings


def sweep_image(photo: Image.Image, args: argparse.Namespace) -> Image.Image:
    values = [value.strip() for value in args.values.split(",") if value.strip()]
    column = PRINT_WIDTH_DOTS // len(values)
    left = max(0, min(args.slice_left, PRINT_WIDTH_DOTS - column))
    columns = []
    for value in values:
        gray = prepare(photo, width=PRINT_WIDTH_DOTS, **_settings(args, value))
        bitmap = dither(gray, args.method)
        if args.erode_min_run:
            bitmap = erode_bottom_edges(bitmap, min_run=args.erode_min_run)
        columns.append((value, bitmap.crop((left, 0, left + column, bitmap.height))))
    height = columns[0][1].height
    sheet = Image.new("1", (PRINT_WIDTH_DOTS, height + LABEL_PX), 1)
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=14)
    for index, (value, image) in enumerate(columns):
        x = index * column
        draw.text((x + 4, 1), f"{args.param} {value}", fill=0, font=font)
        sheet.paste(image, (x, LABEL_PX))
        if index:
            draw.line((x, 0, x, sheet.height), fill=1, width=2)
    return sheet


def main() -> None:
    args = _parse_args()
    try:
        photo = load(args.photo)
    except PhotoError as error:
        sys.exit(f"ERROR: {error}")
    sheet = sweep_image(photo, args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.out)
    print(f"Sweep: {args.out}")
    if args.no_print:
        return
    fixed = {k: v for k, v in _settings(args, "0").items() if k != args.param.replace("-", "_")}
    with open_printer() as p:
        p.text("tone sweep: " + ", ".join(f"{k}={v}" for k, v in fixed.items()) + "\n")
        p.image(sheet, center=False)
        p.ln(3)
    print("Printed.")


if __name__ == "__main__":
    main()
