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

from escpos.constants import HW_INIT
from escpos.printer import Dummy
from PIL import ExifTags, Image, UnidentifiedImageError
from playwright.sync_api import Error as PlaywrightError, sync_playwright

from photo_dither import dither, prepare
from print_profile import DEFAULT_PROFILE, capture_options, join_js, load_gray, to_bitmap
from printer import DOTS_PER_MM, PRINT_WIDTH_DOTS
from raster_capture import capture_receipt, snapshot_mhtml
from ticket_templates import (
    TEXT_FEED, TemplateError, bitmap_from_capture, capture_template, check_envelope, launch_browser, open_render_page,
    render_text,
)

KINDS = ("receipt", "image", "template", "text")
MAX_HEIGHT_DOTS = 500 * DOTS_PER_MM
MAX_SOURCE_PIXELS = 25_000_000
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
    screenshot: bytes | None = None
    mhtml: bytes | None = None


@dataclass(frozen=True)
class _Output:
    bitmap: Image.Image
    screenshot: bytes | None = None
    mhtml: bytes | None = None
    text: bytes | None = None


def render(kind: str, *, payload: dict | None = None, image: bytes | None = None) -> Rendered:
    started = time.perf_counter()
    if kind == "receipt":
        output = _receipt_render(payload)
    elif kind == "image":
        output = _Output(_image_bitmap(image))
    elif kind in ("template", "text"):
        output = _template_render(payload, text=kind == "text")
    else:
        raise RenderError(f"unknown kind {kind!r}; expected one of: {', '.join(KINDS)}")
    bitmap = output.bitmap
    png = io.BytesIO()
    bitmap.save(png, format="PNG")
    return Rendered(
        bitmap=bitmap,
        png=png.getvalue(),
        escpos=_escpos(bitmap) if output.text is None else HW_INIT + output.text + TEXT_FEED,
        width=bitmap.width,
        height=bitmap.height,
        render_ms=round((time.perf_counter() - started) * 1000),
        screenshot=output.screenshot,
        mhtml=output.mhtml,
    )


def _escpos(bitmap: Image.Image) -> bytes:
    printer = Dummy()
    printer.profile.profile_data["media"]["width"]["pixels"] = PRINT_WIDTH_DOTS
    printer.hw("INIT")
    printer.image(bitmap, center=False)
    printer.ln(3)
    return printer.output


def _receipt_render(payload: dict | None) -> _Output:
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
        mhtml = Path(scratch) / "page.mhtml"
        options = capture_options(DEFAULT_PROFILE)
        options["prepare_js"] = join_js(options["prepare_js"], _PROBE_JS)
        try:
            capture_receipt(site, out_png=screenshot, out_mhtml=mhtml, **options)
        except PlaywrightError as error:
            rejected = re.search(re.escape(_REJECT) + r"(?:height=(\d+)|(.*))", str(error))
            if not rejected:
                raise
            if rejected[1]:
                _check_height("receipt", int(rejected[1]))
            raise RenderError(rejected[2]) from None
        gray = load_gray(screenshot)
        _check_height("receipt", gray.height)
        return _Output(to_bitmap(gray, DEFAULT_PROFILE), screenshot.read_bytes(), mhtml.read_bytes())


def _template_render(payload: dict | None, *, text: bool) -> _Output:
    """The preview, with the ESC/POS text body when ``text``."""
    try:
        check_envelope(payload)
        with sync_playwright() as playwright:
            browser = launch_browser(playwright)
            try:
                page = open_render_page(browser)
                body = render_text(page, payload) if text else None
                capture = capture_template(page, payload, max_height_dots=MAX_HEIGHT_DOTS)
                return _Output(bitmap_from_capture(capture), capture.png, snapshot_mhtml(page), body)
            finally:
                browser.close()
    except TemplateError as error:
        raise RenderError(str(error)) from None


def _image_bitmap(data: bytes | None) -> Image.Image:
    if not data:
        raise RenderError("an image job needs a non-empty image")
    try:
        picture = Image.open(io.BytesIO(data))
    except UnidentifiedImageError:
        raise RenderError("the upload is not an image this server can read; send a JPEG or PNG") from None
    except (OSError, Image.DecompressionBombError) as error:
        raise RenderError(f"the upload is not a readable image: {error}") from error
    width, height = picture.size
    limit = min(MAX_SOURCE_PIXELS, Image.MAX_IMAGE_PIXELS)
    if width * height > limit:
        raise RenderError(f"the image has {width * height:,} pixels; the limit is {limit:,}")
    try:
        # PngImagePlugin decodes the pixels here when no eXIf chunk precedes the image data.
        rotated = picture.getexif().get(ExifTags.Base.Orientation) in (5, 6, 7, 8)
        if rotated:
            width, height = height, width
        _check_height("image", max(1, round(height * PRINT_WIDTH_DOTS / width)))
        if picture.format == "JPEG":
            # Decodes at 1/2, 1/4 or 1/8 scale, never below the requested size.
            picture.draft(None, (1, PRINT_WIDTH_DOTS) if rotated else (PRINT_WIDTH_DOTS, 1))
        picture.load()
    except OSError as error:
        raise RenderError(f"the upload is not a readable image: {error}") from error
    return dither(prepare(picture, width=PRINT_WIDTH_DOTS))


def _check_height(what: str, height: int) -> None:
    if height > MAX_HEIGHT_DOTS:
        raise RenderError(
            f"the {what} would print {height / DOTS_PER_MM / 10:.1f} cm long; "
            f"the limit is {MAX_HEIGHT_DOTS / DOTS_PER_MM / 10:.0f} cm"
        )
