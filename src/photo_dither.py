"""Turn a photo into a 1-bit image that survives a 203 DPI thermal head."""

from __future__ import annotations

from PIL import Image, ImageFilter, ImageOps

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


def prepare(
    image: Image.Image,
    *,
    width: int,
    gamma: float = 1.3,
    sharpen: int = 100,
    contrast_cutoff: float = 1.0,
) -> Image.Image:
    """Return a grayscale image ``width`` px wide, toned for thermal paper.

    ``gamma`` > 1 lifts midtones to offset dot gain (printed dots bleed, so
    prints come out darker than the screen preview). ``sharpen`` is an
    unsharp-mask percent; 0 disables it.
    """
    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA", "P"):
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
    if sharpen > 0:
        gray = gray.filter(ImageFilter.UnsharpMask(radius=1.2, percent=sharpen, threshold=2))
    return gray


def dither(gray: Image.Image, method: str = "atkinson", *, serpentine: bool = True) -> Image.Image:
    """Convert a grayscale image to mode ``"1"`` with the named method."""
    if gray.mode != "L":
        gray = gray.convert("L")
    if method == "threshold":
        return gray.point(lambda value: 255 if value >= 128 else 0).convert("1", dither=Image.Dither.NONE)
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
