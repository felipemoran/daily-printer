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
RENDER_TIMEOUT_MS = 3_000
SCREENSHOT_TIMEOUT_MS = 10_000
# The in-page timeout cannot interrupt a busy render; small payloads keep every render short.
MAX_PAYLOAD_BYTES = 64 * 1024

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
  return {
    orientation: receipt.dataset.orientation,
    width: receipt.offsetWidth,
    height: receipt.offsetHeight,
    children: receipt.childElementCount,
  };
}
"""

# The first content the print would clip or lose, as a message, or null. A box clipping its content,
# text spilling out of its block, or a box past the paper edge. In landscape the paper runs down the page.
_FIT_JS = """
([paper, slack]) => {
  const receipt = document.querySelector('#receipt');
  const landscape = receipt.dataset.orientation === 'landscape';
  const origin = receipt.getBoundingClientRect(), style = getComputedStyle(receipt);
  const start = landscape
    ? origin.top + receipt.clientTop + parseFloat(style.paddingTop)
    : origin.left + receipt.clientLeft + parseFloat(style.paddingLeft);
  const quote = (text) => {
    const flat = text.replace(/\\s+/g, ' ').trim();
    return flat.length > 40 ? `"${flat.slice(0, 39)}…"` : flat && `"${flat}"`;
  };
  const name = (el) => quote(el.textContent) || (el.getAttribute('class') ? `<${el.localName} class="${el.getAttribute('class')}">` : `<${el.localName}>`);
  for (const el of receipt.querySelectorAll('*')) {
    const box = el.getBoundingClientRect();
    if (!box.width || !box.height) continue;
    const [low, high] = landscape ? [box.top, box.bottom] : [box.left, box.right];
    if (low < start - slack || high > start + paper + slack) return `content runs past the paper edge: ${name(el)}`;
    const { overflowX, overflowY, lineHeight } = getComputedStyle(el);
    if (overflowX !== 'visible' && el.scrollWidth > el.clientWidth + slack) {
      return `text does not fit: ${name(el)} is wider than its ${el.clientWidth}px cell`;
    }
    // A glyph box taller than its line height (TextMode: 40px JetBrains Mono on 48px lines)
    // overflows by a few dots without clipping ink; a clipped line overflows by a whole line.
    if (overflowY !== 'visible' && el.scrollHeight > el.clientHeight + Math.max(slack, parseFloat(lineHeight) / 2 || 0)) {
      return `text does not fit: ${name(el)} is taller than its ${el.clientHeight}px cell`;
    }
  }
  const walker = document.createTreeWalker(receipt, NodeFilter.SHOW_TEXT), range = document.createRange();
  for (let node; (node = walker.nextNode());) {
    if (!node.data.trim()) continue;
    range.selectNodeContents(node);
    const text = range.getBoundingClientRect();
    if (!text.width) continue;
    let block = node.parentElement;
    while (block !== receipt && ['inline', 'contents'].includes(getComputedStyle(block).display)) block = block.parentElement;
    const left = block.getBoundingClientRect().left + block.clientLeft;
    if (text.left < left - slack || text.right > left + block.clientWidth + slack) {
      return `text does not fit: ${quote(node.data)} is wider than its ${block.clientWidth}px cell`;
    }
  }
  return null;
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
    try:
        size = len(json.dumps(payload, allow_nan=False).encode())
    except (TypeError, ValueError) as error:
        raise TemplateError(f"payload: not JSON ({error})") from error
    if size > MAX_PAYLOAD_BYTES:
        raise TemplateError(f"payload: {size} bytes; the limit is {MAX_PAYLOAD_BYTES}")
    if not isinstance(payload.get("template"), str):
        raise TemplateError("template: expected string")
    version = payload.get("schemaVersion")
    if not isinstance(version, int) or isinstance(version, bool):
        raise TemplateError("schemaVersion: expected integer")
    if not isinstance(payload.get("data"), dict):
        raise TemplateError("data: expected object")


def _length(page, landscape: bool) -> int:
    receipt = page.evaluate(_RECEIPT_JS)
    return receipt["width"] if landscape else receipt["height"]


def _check_unchanged(length: int, now: int, verb: str) -> None:
    if now != length:
        raise TemplateError(f"render was still changing layout (measured {length} dots, {verb} {now})")


def render_template(page, payload, *, max_height_dots: int = 4000) -> Image.Image:
    """``payload`` as a mode "1" bitmap, ``PRINT_WIDTH_DOTS`` wide. Raises TemplateError for sender faults."""
    _check_envelope(payload)
    error = page.evaluate(_RENDER_JS, [payload, RENDER_TIMEOUT_MS])
    if error:
        raise TemplateError(error)
    if _CAPTURE["prepare_js"]:
        page.evaluate(_CAPTURE["prepare_js"])
    receipt = page.evaluate(_RECEIPT_JS)
    if not receipt["children"]:
        raise TemplateError(f'template "{payload["template"]}" rendered nothing')
    landscape = receipt["orientation"] == "landscape"
    length = receipt["width"] if landscape else receipt["height"]
    if length > max_height_dots:
        raise TemplateError(f"render is {length} dots long; the limit is {max_height_dots}")
    misfit = page.evaluate(_FIT_JS, [PRINT_WIDTH_DOTS, 1])
    if misfit:
        raise TemplateError(misfit)
    # A screenshot can resize the viewport and reflow the page, but it keeps the clip it measured
    # first: the print then ends in a band of page canvas or loses its end.
    _check_unchanged(length, _length(page, landscape), "then")
    image = Image.open(io.BytesIO(page.locator("#receipt").screenshot(timeout=SCREENSHOT_TIMEOUT_MS)))
    _check_unchanged(length, image.width if landscape else image.height, "captured")
    _check_unchanged(length, _length(page, landscape), "then")
    if landscape:
        image = image.transpose(Image.Transpose.ROTATE_270)
    if image.width != PRINT_WIDTH_DOTS:
        raise RuntimeError(f"#receipt captured {image.width} dots across the paper, not {PRINT_WIDTH_DOTS}")
    bitmap = to_bitmap(to_gray(image), DEFAULT_PROFILE)
    return bitmap if bitmap.mode == "1" else bitmap.convert("1")
