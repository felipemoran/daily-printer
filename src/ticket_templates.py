"""Render template payloads to 1-bit rasters through web/dist/render.html: docs/feature-ticket-templates.md."""

from __future__ import annotations

import io
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from PIL import Image

from print_profile import DEFAULT_PROFILE, capture_options, to_bitmap, to_gray
from printer import PRINT_WIDTH_DOTS
from raster_capture import _ALIASED_TEXT_CSS

DIST = (Path(__file__).resolve().parents[1] / "web" / "dist").resolve()
ORIGIN = "http://render.invalid"
LOAD_TIMEOUT_MS = 15_000
RENDER_TIMEOUT_MS = 4_000
SCREENSHOT_TIMEOUT_MS = 10_000

_CAPTURE = capture_options(DEFAULT_PROFILE)

# Resolves to null or the sender-readable message, so a page error never looks like a Playwright fault.
_RENDER_JS = """
async ([payload, timeout]) => {
  let timer;
  const expired = new Promise((resolve) => {
    timer = setTimeout(() => resolve(`render did not finish within ${timeout} ms`), timeout);
  });
  const rendered = window.renderTemplate(payload)
    .then(() => null, (error) => (error instanceof Error ? error.message : String(error)));
  try {
    return await Promise.race([rendered, expired]);
  } finally {
    clearTimeout(timer);
  }
}
"""

_RECEIPT_JS = """
() => {
  const receipt = document.querySelector('#receipt');
  return { orientation: receipt.dataset.orientation, width: receipt.offsetWidth, height: receipt.offsetHeight };
}
"""


class TemplateError(ValueError):
    """The payload is wrong; the message tells the sender what to fix."""


def _dist_file(name: str) -> Path:
    path = DIST / name
    if not path.is_file():
        raise RuntimeError(f"{path} is missing. Run: make web-build")
    return path


def template_names() -> list[str]:
    return json.loads(_dist_file("templates.json").read_text(encoding="utf-8"))


def _serve(route) -> None:
    file = (DIST / unquote(urlsplit(route.request.url).path).lstrip("/")).resolve()
    if file.is_file() and file.is_relative_to(DIST):
        route.fulfill(path=file)
    else:
        route.fulfill(status=404)


def open_render_page(browser):
    """A page on render.html, ready for any number of ``render_template`` calls."""
    _dist_file("render.html")
    page = browser.new_page(viewport={"width": PRINT_WIDTH_DOTS, "height": 720}, device_scale_factor=1)
    page.set_default_timeout(LOAD_TIMEOUT_MS)
    # Routes run newest first: files from web/dist, nothing from the network.
    page.route("**/*", lambda route: route.abort())
    page.route(f"{ORIGIN}/**", _serve)
    page.goto(f"{ORIGIN}/render.html", wait_until="load", timeout=LOAD_TIMEOUT_MS)
    if _CAPTURE["aliased_text"]:
        page.add_style_tag(content=_ALIASED_TEXT_CSS)
    if _CAPTURE["extra_css"]:
        page.add_style_tag(content=_CAPTURE["extra_css"])
    return page


def _check_envelope(payload) -> None:
    if not isinstance(payload, dict):
        raise TemplateError("payload: expected object")
    if not isinstance(payload.get("template"), str):
        raise TemplateError("template: expected string")
    version = payload.get("schemaVersion")
    if not isinstance(version, int) or isinstance(version, bool):
        raise TemplateError("schemaVersion: expected integer")
    if not isinstance(payload.get("data"), dict):
        raise TemplateError("data: expected object")


def render_template(page, payload, *, max_height_dots: int = 4000) -> Image.Image:
    """``payload`` as a mode "1" bitmap, ``PRINT_WIDTH_DOTS`` wide. Raises TemplateError for sender faults."""
    _check_envelope(payload)
    error = page.evaluate(_RENDER_JS, [payload, RENDER_TIMEOUT_MS])
    if error:
        raise TemplateError(error)
    if _CAPTURE["prepare_js"]:
        page.evaluate(_CAPTURE["prepare_js"])
    receipt = page.evaluate(_RECEIPT_JS)
    landscape = receipt["orientation"] == "landscape"
    length = receipt["width"] if landscape else receipt["height"]
    if length > max_height_dots:
        raise TemplateError(f"render is {length} dots long; the limit is {max_height_dots}")
    image = Image.open(io.BytesIO(page.locator("#receipt").screenshot(timeout=SCREENSHOT_TIMEOUT_MS)))
    if landscape:
        image = image.transpose(Image.Transpose.ROTATE_270)
    bitmap = to_bitmap(to_gray(image), DEFAULT_PROFILE)
    return bitmap if bitmap.mode == "1" else bitmap.convert("1")
