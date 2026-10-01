"""Turn a photo into a 1-bit image that survives a 203 DPI thermal head."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps, UnidentifiedImageError

# (divisor, taps). Each tap is (dx, dy, weight); dx is mirrored on reversed rows.
_KERNELS: dict[str, tuple[int, tuple[tuple[int, int, int], ...]]] = {
    "floyd-steinberg": (16, ((1, 0, 7), (-1, 1, 3), (0, 1, 5), (1, 1, 1))),
    # Diffuses only 6/8 of the error: highlights stay clean, shadows go solid.
    "atkinson": (8, ((1, 0, 1), (2, 0, 1), (-1, 1, 1), (0, 1, 1), (1, 1, 1), (0, 2, 1))),
    "jarvis": (48, (
        (1, 0, 7), (2, 0, 5),
        (-2, 1, 3), (-1, 1, 5), (0, 1, 7), (1, 1, 5), (2, 1, 3),
        (-2, 2, 1), (-1, 2, 3), (0, 2, 5), (1, 2, 3), (2, 2, 1),
    )),
    "stucki": (42, (
        (1, 0, 8), (2, 0, 4),
        (-2, 1, 2), (-1, 1, 4), (0, 1, 8), (1, 1, 4), (2, 1, 2),
        (-2, 2, 1), (-1, 2, 2), (0, 2, 4), (1, 2, 2), (2, 2, 1),
    )),
}

METHODS = ("atkinson", "floyd-steinberg", "jarvis", "stucki", "bayer", "threshold")


class PhotoError(Exception):
    pass


def load(path: Path) -> Image.Image:
    """Open and decode ``path``; raise ``PhotoError`` with a user-facing message."""
    if not path.is_file():
        raise PhotoError(f"photo not found: {path}")
    try:
        image = Image.open(path)
        image.load()
        return image
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        message = f"not a readable image: {path}\n  {error}"
        if path.suffix.lower() in (".heic", ".heif"):
            message += (
                "\n  Pillow cannot read HEIC. Convert it first:"
                f"\n  sips -s format jpeg '{path}' --out '{path.with_suffix('.jpg')}'"
            )
        raise PhotoError(message) from error


def prepare(
    image: Image.Image,
    *,
    width: int,
    gamma: float = 1.3,
    sharpen: int = 100,
    contrast_cutoff: float = 1.0,
    black_point: int = 0,
    white_point: int = 255,
) -> Image.Image:
    """Return a grayscale image ``width`` px wide, toned for thermal paper.

    ``gamma`` > 1 lifts midtones to offset dot gain (printed dots bleed, so
    prints come out darker than the screen preview). ``black_point`` and
    ``white_point`` rescale the tones linearly into that range: near-black
    areas keep white dots that dot gain would fill, and light skin keeps
    dots instead of washing out. ``sharpen`` is an unsharp-mask
    percent; 0 disables it.
    """
    image = ImageOps.exif_transpose(image)
    if image.mode.startswith("I;16") or image.mode == "I":
        # convert("L") clips 16-bit values instead of scaling them.
        image = image.convert("I").point(lambda value: value / 256)
    if "A" in image.getbands() or "transparency" in image.info:
        image = image.convert("RGBA")
        background = Image.new("RGBA", image.size, (255, 255, 255, 255))
        image = Image.alpha_composite(background, image)
    gray = image.convert("L")

    height = max(1, round(gray.height * width / gray.width))
    gray = gray.resize((width, height), Image.Resampling.LANCZOS)

    if contrast_cutoff > 0:
        gray = ImageOps.autocontrast(gray, cutoff=contrast_cutoff)
    if gamma != 1.0:
        lut = [round(255 * (value / 255) ** (1 / gamma)) for value in range(256)]
        gray = gray.point(lut)
    if (black_point, white_point) != (0, 255):
        span = white_point - black_point
        gray = gray.point([round(black_point + value * span / 255) for value in range(256)])
    if sharpen > 0:
        gray = gray.filter(ImageFilter.UnsharpMask(radius=1.2, percent=sharpen, threshold=2))
    return gray


def dither(gray: Image.Image, method: str = "atkinson", *, serpentine: bool = True) -> Image.Image:
    """Convert a grayscale image to mode ``"1"`` with the named method."""
    if gray.mode != "L":
        gray = gray.convert("L")
    if method == "threshold":
        return gray.point(lambda value: 255 if value >= 128 else 0, mode="1")
    if method == "bayer":
        return _bayer(gray)
    if method in _KERNELS:
        divisor, taps = _KERNELS[method]
        return _diffuse(gray, divisor, taps, serpentine)
    raise ValueError(f"unknown dither method {method!r}; choose from {', '.join(METHODS)}")


def _diffuse(
    gray: Image.Image,
    divisor: int,
    taps: tuple[tuple[int, int, int], ...],
    serpentine: bool,
) -> Image.Image:
    width, height = gray.size
    pixels = [float(value) for value in gray.tobytes()]
    out = bytearray(width * height)
    for y in range(height):
        reverse = serpentine and y % 2 == 1
        direction = -1 if reverse else 1
        columns = range(width - 1, -1, -1) if reverse else range(width)
        row = y * width
        for x in columns:
            index = row + x
            old = pixels[index]
            new = 255 if old >= 128 else 0
            out[index] = new
            error = (old - new) / divisor
            if error == 0:
                continue
            for dx, dy, weight in taps:
                nx = x + dx * direction
                ny = y + dy
                if 0 <= nx < width and ny < height:
                    pixels[ny * width + nx] += error * weight
    return Image.frombytes("L", (width, height), bytes(out)).convert("1", dither=Image.Dither.NONE)


def _bayer_matrix(size: int) -> list[list[int]]:
    matrix = [[0]]
    while len(matrix) < size:
        n = len(matrix)
        matrix = [
            [4 * matrix[y % n][x % n] + (0, 2, 3, 1)[(y // n) * 2 + (x // n)] for x in range(2 * n)]
            for y in range(2 * n)
        ]
    return matrix


def _bayer(gray: Image.Image, size: int = 8) -> Image.Image:
    matrix = _bayer_matrix(size)
    levels = size * size
    thresholds = [[(cell + 0.5) * 255 / levels for cell in row] for row in matrix]
    width, height = gray.size
    source = gray.tobytes()
    out = bytearray(width * height)
    for y in range(height):
        row_thresholds = thresholds[y % size]
        row = y * width
        for x in range(width):
            out[row + x] = 255 if source[row + x] > row_thresholds[x % size] else 0
    return Image.frombytes("L", (width, height), bytes(out)).convert("1", dither=Image.Dither.NONE)


def erode_bottom_edges(bitmap: Image.Image, *, min_run: int = 3) -> Image.Image:
    """Drop the bottom dot of every vertical black run at least ``min_run`` dots tall.

    The head is still hot from the row it just burned, so the row below a
    stroke prints dark; pre-removing it cancels that smear. Text stems are long
    runs; dithered greys are mostly 1-2 dot runs, so ``min_run`` 3 spares them.
    Pixels outside the image count as white.
    """
    if min_run < 2:
        raise ValueError(f"min_run must be >= 2, got {min_run}")
    ink = bitmap.convert("L").point(lambda value: 255 if value < 128 else 0, mode="1")
    run = ink
    for rows_up in range(1, min_run):
        run = ImageChops.logical_and(run, _shift_down(ink, rows_up))
    below_is_white = ImageChops.invert(_shift_down(ink, -1).convert("L")).convert("1")
    remove = ImageChops.logical_and(run, below_is_white)
    kept_ink = ImageChops.subtract(ink.convert("L"), remove.convert("L"))
    return kept_ink.point(lambda value: 0 if value else 255, mode="1")


def _shift_down(image: Image.Image, rows: int) -> Image.Image:
    """Move content down by ``rows`` (up when negative); vacated rows are 0."""
    out = Image.new(image.mode, image.size, 0)
    out.paste(image.crop((0, max(0, -rows), image.width, image.height - max(0, rows))), (0, max(0, rows)))
    return out
