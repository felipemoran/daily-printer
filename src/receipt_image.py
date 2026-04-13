"""Prepare a screenshot PNG for python-escpos raster printing."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


def prepare_for_escpos(
    png_path: Path,
    *,
    target_width: int,
    dither: bool,
) -> Image.Image:
    """Load a PNG, normalize to monochrome, width ``target_width`` (dots)."""
    im = Image.open(png_path)
    im = im.convert("RGBA") if im.mode == "P" else im
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[3])
        im = bg
    elif im.mode != "RGB":
        im = im.convert("RGB")

    im = im.convert("L")
    w, h = im.size
    if w != target_width:
        new_h = max(1, round(h * (target_width / w)))
        im = im.resize((target_width, new_h), Image.Resampling.LANCZOS)

    if dither:
        return im.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    return im.point(lambda p: 255 if p > 200 else 0, mode="1")
