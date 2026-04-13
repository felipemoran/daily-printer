"""Vertical splitting of receipt rasters (stub for long jobs)."""

from __future__ import annotations

from PIL import Image


def split_raster_vertical(image: Image.Image, max_height_px: int) -> list[Image.Image]:
    """Return one or more horizontal strips for ESC/POS.

    v1: always returns a single image. When receipts exceed ``max_height_px``,
    implement slicing here and update callers to print each strip in order.
    """
    _ = max_height_px
    return [image]
