"""Job content to a 1-bit bitmap, its PNG and the ESC/POS bytes that print it."""

from __future__ import annotations

import io
import json
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from escpos.printer import Dummy
from PIL import ExifTags, Image, UnidentifiedImageError
from playwright.sync_api import Error as PlaywrightError

from photo_dither import dither, prepare
from print_profile import DEFAULT_PROFILE, capture_options, join_js, load_gray, to_bitmap
from printer import PRINT_WIDTH_DOTS
from raster_capture import capture_receipt

KINDS = ("receipt", "image")
MAX_HEIGHT_DOTS = 4000  # 50 cm at 8 dots/mm
DIST_DIR = Path(__file__).resolve().parents[1] / "web" / "dist"

_REJECT = "RENDER_JOB_REJECT:"
# The app has no error boundary: a payload it cannot render unmounts the root,
# and without this check the screenshot waits 30 s for a #receipt that never appears.
# A receipt still loading is a server fault, so that check throws without the marker.
_PROBE_JS = """
() => {
  const reject = (reason) => { throw new Error('%(marker)s' + reason.replace(/\\s+/g, ' ')); };
  const receipt = document.querySelector('#receipt');
  if (!receipt) reject('the receipt app could not render the payload; check the blocks');
  if (receipt.querySelector(':scope > p.muted:only-child'))
    throw new Error('the receipt app was still loading the payload at capture time');
  if (receipt.classList.contains('receipt--error'))
    reject('the receipt app rejected the payload: ' + receipt.querySelector('.error-body')?.textContent);
  if (receipt.offsetHeight > %(max_height)d) reject('height=' + receipt.offsetHeight);
}
""" % {"marker": _REJECT, "max_height": MAX_HEIGHT_DOTS}


class RenderError(Exception):
    """A content problem the sender can fix."""


@dataclass(frozen=True)
class Rendered:
    bitmap: Image.Image
    png: bytes
    escpos: bytes
    width: int
    height: int
    render_ms: int


def render(kind: str, *, payload: dict | None = None, image: bytes | None = None) -> Rendered:
    started = time.perf_counter()
    if kind == "receipt":
        bitmap = _receipt_bitmap(payload)
    elif kind == "image":
        bitmap = _image_bitmap(image)
    else:
        raise RenderError(f"unknown kind {kind!r}; expected one of: {', '.join(KINDS)}")
    png = io.BytesIO()
    bitmap.save(png, format="PNG")
    return Rendered(
        bitmap=bitmap,
        png=png.getvalue(),
        escpos=_escpos(bitmap),
        width=bitmap.width,
        height=bitmap.height,
        render_ms=round((time.perf_counter() - started) * 1000),
    )


def escpos_from_png(png: bytes) -> bytes:
    return _escpos(Image.open(io.BytesIO(png)))


def _escpos(bitmap: Image.Image) -> bytes:
    printer = Dummy()
    printer.profile.profile_data["media"]["width"]["pixels"] = PRINT_WIDTH_DOTS
    printer.hw("INIT")
    printer.image(bitmap, center=False)
    printer.ln(3)
    return printer.output


def _receipt_bitmap(payload: dict | None) -> Image.Image:
    if payload is None:
        raise RenderError("a receipt job needs a payload")
    if not isinstance(payload, dict):
        raise RenderError("the receipt payload must be a JSON object")
    if not (DIST_DIR / "index.html").is_file():
        raise RuntimeError(f"{DIST_DIR / 'index.html'} is missing; build the receipt app with `make web-build`")
    with tempfile.TemporaryDirectory(prefix="render-job-") as scratch:
        # The app always fetches /payload.json, so each render serves its own copy of the site.
        site = Path(scratch) / "site"
        shutil.copytree(DIST_DIR, site)
        (site / "payload.json").write_text(json.dumps(payload), encoding="utf-8")
        screenshot = Path(scratch) / "receipt.png"
        options = capture_options(DEFAULT_PROFILE)
        options["prepare_js"] = join_js(options["prepare_js"], _PROBE_JS)
        try:
            capture_receipt(site, out_png=screenshot, **options)
        except PlaywrightError as error:
            rejected = re.search(re.escape(_REJECT) + r"(?:height=(\d+)|(.*))", str(error))
            if not rejected:
                raise
            if rejected[1]:
                _check_height("receipt", int(rejected[1]))
            raise RenderError(rejected[2]) from None
        gray = load_gray(screenshot)
        _check_height("receipt", gray.height)
        return to_bitmap(gray, DEFAULT_PROFILE)


def _image_bitmap(data: bytes | None) -> Image.Image:
    if not data:
        raise RenderError("an image job needs a non-empty image")
    try:
        picture = Image.open(io.BytesIO(data))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise RenderError(f"the upload is not a readable image: {error}") from error
    width, height = picture.size
    if width * height > Image.MAX_IMAGE_PIXELS:
        raise RenderError(f"the image has {width * height:,} pixels; the limit is {Image.MAX_IMAGE_PIXELS:,}")
    try:
        # PngImagePlugin decodes the pixels here when no eXIf chunk precedes the image data.
        if picture.getexif().get(ExifTags.Base.Orientation) in (5, 6, 7, 8):
            width, height = height, width
        _check_height("image", max(1, round(height * PRINT_WIDTH_DOTS / width)))
        picture.load()
    except OSError as error:
        raise RenderError(f"the upload is not a readable image: {error}") from error
    return dither(prepare(picture, width=PRINT_WIDTH_DOTS))


def _check_height(what: str, height: int) -> None:
    if height > MAX_HEIGHT_DOTS:
        raise RenderError(
            f"the {what} would print {height / 80:.1f} cm long; the limit is {MAX_HEIGHT_DOTS / 80:.0f} cm"
        )
