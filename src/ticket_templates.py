"""Render template payloads through web/dist/render.html, to 1-bit rasters or native ESC/POS text: docs/feature-ticket-templates.md."""

from __future__ import annotations

import io
import json
import math
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from escpos.constants import CODEPAGE_CHANGE, FS, LINESPACING_RESET, TXT_SIZE
from PIL import Image

from print_profile import DEFAULT_PROFILE, capture_options, to_bitmap, to_gray
from printer import PRINT_WIDTH_DOTS
from raster_capture import ALIASED_TEXT_CSS

DIST = (Path(__file__).resolve().parents[1] / "web" / "dist").resolve()
ORIGIN = "http://render.invalid"
LOAD_TIMEOUT_MS = 15_000
RENDER_TIMEOUT_MS = 3_000
SCREENSHOT_TIMEOUT_MS = 10_000
# The in-page timeout cannot interrupt a busy render; small payloads keep every render short.
MAX_PAYLOAD_BYTES = 64 * 1024
# page.evaluate hangs past 30 s on an argument about 145 levels deep; deeper ones raise RecursionError
# or PlaywrightError. Real payloads nest 6 levels deep.
MAX_DEPTH = 32

_CAPTURE = capture_options(DEFAULT_PROFILE)
VIEWPORT_MARGIN = 64
DOTS_PER_CM = 80
SERVER_FAULT = "server fault: "

# Resolves to [null, result] or [message, null], so a page error never looks like a Playwright fault.
_CALL_JS = """
async ([name, payload, timeout]) => {
  if (typeof window[name] !== 'function') return [`server fault: render.html has no ${name}; rebuild web/dist`, null];
  let timer;
  const expired = new Promise((resolve) => {
    timer = setTimeout(() => resolve([`render did not finish within ${timeout} ms`, null]), timeout);
  });
  const called = Promise.resolve().then(() => window[name](payload))
    .then((result) => [null, result ?? null], (error) => [error instanceof Error ? error.message : String(error), null]);
  try {
    return await Promise.race([called, expired]);
  } finally {
    clearTimeout(timer);
  }
}
"""

_RECEIPT_JS = """
() => {
  const receipt = document.querySelector('#receipt'), box = receipt.getBoundingClientRect();
  // Rounded up like the screenshot clip; offsetHeight rounds to nearest.
  return {
    orientation: receipt.dataset.orientation,
    width: Math.ceil(box.width),
    height: Math.ceil(box.height),
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
  const outside = (low, high, tolerance) => low < start - tolerance || high > start + paper + tolerance;
  // Glyph boxes overhang their line box by a few dots without clipping ink (TextMode: 1-2 dots).
  const overhang = slack + 2;
  const name = (el) => quote(el.textContent) || (el.getAttribute('class') ? `<${el.localName} class="${el.getAttribute('class')}">` : `<${el.localName}>`);
  for (const el of receipt.querySelectorAll('*')) {
    const box = el.getBoundingClientRect();
    if (box.width && box.height && outside(...(landscape ? [box.top, box.bottom] : [box.left, box.right]), slack)) {
      return `content runs past the paper edge: ${name(el)}`;
    }
    const { overflowX, overflowY } = getComputedStyle(el);
    if (overflowX !== 'visible' && el.scrollWidth > el.clientWidth + slack) {
      return `text does not fit: ${name(el)} is wider than its ${el.clientWidth}px cell`;
    }
    if (overflowY !== 'visible' && el.scrollHeight > el.clientHeight + overhang) {
      return `text does not fit: ${name(el)} is taller than its ${el.clientHeight}px cell`;
    }
  }
  const walker = document.createTreeWalker(receipt, NodeFilter.SHOW_TEXT), range = document.createRange();
  for (let node; (node = walker.nextNode());) {
    if (!node.data.trim()) continue;
    range.selectNodeContents(node);
    const text = range.getBoundingClientRect();
    if (!text.width) continue;
    if (outside(...(landscape ? [text.top, text.bottom] : [text.left, text.right]), overhang)) {
      return `content runs past the paper edge: ${quote(node.data)}`;
    }
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
        page.add_style_tag(content=ALIASED_TEXT_CSS)
    if _CAPTURE["extra_css"]:
        page.add_style_tag(content=_CAPTURE["extra_css"])
    return page


def _deeper_than(value, limit: int) -> bool:
    stack = [(value, 1)]
    while stack:
        value, depth = stack.pop()
        if isinstance(value, (dict, list, tuple)):
            if depth > limit:
                return True
            stack.extend((child, depth + 1) for child in (value.values() if isinstance(value, dict) else value))
    return False


def check_envelope(payload) -> None:
    """Raises TemplateError for an envelope render.html would refuse, without a browser."""
    if not isinstance(payload, dict):
        raise TemplateError("payload: expected object")
    if _deeper_than(payload, MAX_DEPTH):
        raise TemplateError(f"payload: nested more than {MAX_DEPTH} levels deep")
    try:
        size = len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode())
    except (TypeError, ValueError) as error:
        raise TemplateError(f"payload: not JSON ({error})") from error
    if size > MAX_PAYLOAD_BYTES:
        raise TemplateError(f"payload: {size} bytes; the limit is {MAX_PAYLOAD_BYTES}")
    name = payload.get("template")
    if not isinstance(name, str):
        raise TemplateError("template: expected string")
    version = payload.get("schemaVersion")
    if not isinstance(version, int) or isinstance(version, bool):
        raise TemplateError("schemaVersion: expected integer")
    if not isinstance(payload.get("data"), dict):
        raise TemplateError("data: expected object")
    names = template_names()
    if name not in names:
        raise TemplateError(f'unknown template "{name}"; known: {", ".join(sorted(names))}')


def _length(page, landscape: bool) -> int:
    receipt = page.evaluate(_RECEIPT_JS)
    return receipt["width"] if landscape else receipt["height"]


def _cover_receipt(page, landscape: bool, length: int) -> None:
    across = PRINT_WIDTH_DOTS + VIEWPORT_MARGIN
    page.set_viewport_size({"width": length + VIEWPORT_MARGIN, "height": across} if landscape
                           else {"width": PRINT_WIDTH_DOTS, "height": length + VIEWPORT_MARGIN})
    page.evaluate("() => new Promise((resolve) => requestAnimationFrame(() => setTimeout(resolve)))")


def _check_unchanged(length: int, now: int, verb: str) -> None:
    if now != length:
        raise TemplateError(f"render was still changing layout (measured {length} dots, {verb} {now})")


def _call(page, name: str, payload):
    check_envelope(payload)
    error, result = page.evaluate(_CALL_JS, [name, payload, RENDER_TIMEOUT_MS])
    if error is None:
        return result
    if error.startswith(SERVER_FAULT):
        raise RuntimeError(error)
    raise TemplateError(error)


@dataclass(frozen=True)
class Capture:
    """The ``#receipt`` screenshot as Chromium returned it: across the paper, or along it when ``landscape``."""

    png: bytes
    landscape: bool


def capture_template(page, payload, *, max_height_dots: int = 4000) -> Capture:
    """Render ``payload`` and screenshot it. Raises TemplateError for sender faults."""
    _call(page, "renderTemplate", payload)
    if _CAPTURE["prepare_js"]:
        page.evaluate(_CAPTURE["prepare_js"])
    receipt = page.evaluate(_RECEIPT_JS)
    if not receipt["children"]:
        raise TemplateError(f'template "{payload["template"]}" rendered nothing')
    landscape = receipt["orientation"] == "landscape"
    # A screenshot past the viewport resizes it, and Chrome can then draw glyphs the bundled fonts
    # lack from another system face (Times-Bold, then Menlo-Bold). Resize first, then measure.
    _cover_receipt(page, landscape, min(receipt["width"] if landscape else receipt["height"], max_height_dots))
    length = _length(page, landscape)
    if length > max_height_dots:
        raise TemplateError(f"the receipt would print {math.ceil(length / DOTS_PER_CM * 10) / 10} cm long; "
                            f"the limit is {max_height_dots / DOTS_PER_CM:g} cm")
    misfit = page.evaluate(_FIT_JS, [PRINT_WIDTH_DOTS, 1])
    if misfit:
        raise TemplateError(misfit)
    # A screenshot can resize the viewport and reflow the page, but it keeps the clip it measured
    # first: the print then ends in a band of page canvas or loses its end.
    _check_unchanged(length, _length(page, landscape), "then")
    png = page.locator("#receipt").screenshot(timeout=SCREENSHOT_TIMEOUT_MS)
    image = Image.open(io.BytesIO(png))
    _check_unchanged(length, image.width if landscape else image.height, "captured")
    _check_unchanged(length, _length(page, landscape), "then")
    return Capture(png, landscape)


def bitmap_from_capture(capture: Capture) -> Image.Image:
    """The capture as a mode "1" bitmap, ``PRINT_WIDTH_DOTS`` wide."""
    image = Image.open(io.BytesIO(capture.png))
    if capture.landscape:
        image = image.transpose(Image.Transpose.ROTATE_270)
    if image.width != PRINT_WIDTH_DOTS:
        raise RuntimeError(f"#receipt captured {image.width} dots across the paper, not {PRINT_WIDTH_DOTS}")
    bitmap = to_bitmap(to_gray(image), DEFAULT_PROFILE)
    if bitmap.mode != "1":
        raise RuntimeError(f'to_bitmap returned mode "{bitmap.mode}", not "1"')
    return bitmap


def render_template(page, payload, *, max_height_dots: int = 4000) -> Image.Image:
    """``payload`` as a mode "1" bitmap, ``PRINT_WIDTH_DOTS`` wide. Raises TemplateError for sender faults."""
    return bitmap_from_capture(capture_template(page, payload, max_height_dots=max_height_dots))


# PC437, the ESC/POS power-on default, and its bytes for the bar glyphs. Unverified on the MPT-II
# (design-system/verify.md, Text mode).
CODE_PAGE = CODEPAGE_CHANGE + b"\x00"
GLYPH_BYTES = {"\u2588": 0xDB, "\u2591": 0xB0}
# Generic printers can start in Chinese double-byte mode, where 0xDB 0xDB prints one Chinese glyph.
# FS . leaves it; the body cannot restore a state it cannot read.
KANJI_OFF = FS + b"."
LINE_SPACING_24 = b"\x1b3\x18"
DOUBLE_ON, DOUBLE_OFF = TXT_SIZE + b"\x11", TXT_SIZE + b"\x00"
REVERSE_ON, REVERSE_OFF = b"\x1dB\x01", b"\x1dB\x00"


def _encode(text: str) -> bytes:
    encoded = bytearray()
    for char in text:
        if char in GLYPH_BYTES:
            encoded.append(GLYPH_BYTES[char])
        elif " " <= char <= "~":
            encoded.append(ord(char))
        else:
            raise RuntimeError(f"text-mode line holds {char!r}, which Font A cannot print")
    return bytes(encoded)


TEXT_FEED = b"\n" * 3


def render_text(page, payload) -> bytes:
    """``payload`` as native ESC/POS Font A text: the body only, with no cut.

    The caller sends ``HW_INIT`` before it and ``TEXT_FEED`` after it.

    Breaks lines where ``render_template`` previews them. Raises TemplateError for sender faults.
    """
    body = bytearray(KANJI_OFF + LINE_SPACING_24 + CODE_PAGE)
    for line in _call(page, "templateLines", payload):
        text = _encode(line["text"])
        if line.get("double"):
            text = DOUBLE_ON + text + DOUBLE_OFF
        if line.get("reverse"):
            text = REVERSE_ON + text + REVERSE_OFF
        # LF after every line, a full 32-column one too. Unverified: firmware that auto-wraps at column 32
        # would then feed a blank line.
        body += text + b"\n"
    return bytes(body + LINESPACING_RESET)
