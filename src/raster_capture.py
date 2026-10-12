"""Serve ``web/dist`` over loopback and capture the ``#receipt`` node as PNG with Playwright."""

from __future__ import annotations

import contextlib
import socket
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError, sync_playwright


def _pick_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


def _make_handler(root: Path):
    root_str = str(root.resolve())

    class _Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=root_str, **kwargs)

        def log_message(self, format: str, *log_args) -> None:  # noqa: A003
            return

    return _Handler


@contextlib.contextmanager
def static_server(root: Path, host: str = "127.0.0.1"):
    port = _pick_free_port(host)
    handler = _make_handler(root)
    server = ThreadingHTTPServer((host, port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


_MEASURE_JS = """
(selector) => {
  const origin = document.querySelector('#receipt').getBoundingClientRect();
  return [...document.querySelectorAll(selector)].map((el) => {
    const r = el.getBoundingClientRect();
    return {
      x: r.left - origin.left,
      y: r.top - origin.top,
      width: r.width,
      height: r.height,
      naturalWidth: el.naturalWidth ?? null,
      naturalHeight: el.naturalHeight ?? null,
    };
  });
}
"""


# Text line heights leave later elements at fractional y; Chromium then resamples
# images painted there, which wrecks pre-dithered bitmaps.
_SNAP_JS = """
(selector) => {
  const origin = document.querySelector('#receipt').getBoundingClientRect();
  for (const el of document.querySelectorAll(selector)) {
    const r = el.getBoundingClientRect();
    const dx = Math.ceil(r.left - origin.left) - (r.left - origin.left);
    const dy = Math.ceil(r.top - origin.top) - (r.top - origin.top);
    if (!dx && !dy) continue;
    // Offsets, not margins: a margin can collapse into a neighbour's and vanish.
    const style = getComputedStyle(el);
    if (style.position === 'static') el.style.position = 'relative';
    el.style.left = `${(parseFloat(style.left) || 0) + dx}px`;
    el.style.top = `${(parseFloat(style.top) || 0) + dy}px`;
  }
}
"""


# Honoured by headless Chromium on macOS: glyphs come out 1-bit, so the
# threshold neither fattens nor thins strokes.
ALIASED_TEXT_CSS = "* { -webkit-font-smoothing: none !important; }"

# Chromium's MHTML writer keeps images and style sheets but drops web fonts (seen on Chromium 145).
# A copy of each fetched @font-face rule with its file as a data: URL puts the font into a style sheet part.
_INLINE_FONTS_JS = """
async () => {
  const fetched = new Set(performance.getEntriesByType('resource').map((entry) => entry.name));
  const rules = [];
  for (const sheet of document.styleSheets) {
    for (const rule of sheet.cssRules) {
      if (!(rule instanceof CSSFontFaceRule)) continue;
      const source = /url\\((["']?)([^"')]+)\\1\\)/.exec(rule.style.getPropertyValue('src'));
      const url = source && new URL(source[2], sheet.href ?? document.baseURI).href;
      if (!url || !fetched.has(url)) continue;
      const response = await fetch(url);
      if (!response.ok) throw new Error(`the font ${url} answered HTTP ${response.status}`);
      const blob = await response.blob();
      const data = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(blob);
      });
      rules.push(rule.cssText.replace(source[0], `url("${data}")`));
    }
  }
  const style = document.createElement('style');
  style.textContent = rules.join('\\n');
  document.head.append(style);
}
"""


def snapshot_mhtml(page) -> bytes:
    """The page with its style sheets, images and the fonts it fetched, as Chromium's MHTML."""
    try:
        page.evaluate(_INLINE_FONTS_JS)
    except PlaywrightError as error:
        raise RuntimeError(f"cannot put the page's fonts in its MHTML snapshot: {error.message}") from None
    session = page.context.new_cdp_session(page)
    try:
        return session.send("Page.captureSnapshot", {"format": "mhtml"})["data"].encode()
    finally:
        session.detach()


def capture_receipt(
    dist_dir: Path,
    *,
    host: str = "127.0.0.1",
    index_path: str = "/index.html",
    out_png: Path,
    out_mhtml: Path | None = None,
    device_scale_factor: float = 1.0,
    measure_selector: str | None = None,
    snap_selector: str | None = None,
    aliased_text: bool = False,
    extra_css: str | None = None,
    prepare_js: str | None = None,
) -> tuple[str, list[dict]]:
    """Serve ``dist_dir``, screenshot ``#receipt`` to ``out_png``, and snapshot the page to ``out_mhtml`` when given.
    Return the page URL and CSS-pixel boxes (relative to ``#receipt``) of every element matching ``measure_selector``. Elements matching
    ``snap_selector`` are nudged onto whole pixels before the screenshot.
    ``aliased_text`` turns off text anti-aliasing; ``extra_css`` is injected after load; ``prepare_js`` (a function
    expression) runs after that, before snapping and the screenshot."""
    dist_dir = dist_dir.resolve()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    boxes: list[dict] = []

    with static_server(dist_dir, host=host) as port:
        url = f"http://{host}:{port}{index_path}"
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = browser.new_page(
                        device_scale_factor=device_scale_factor,
                        viewport={"width": 384, "height": 720},
                    )
                    page.goto(url, wait_until="networkidle", timeout=60_000)
                    if aliased_text:
                        page.add_style_tag(content=ALIASED_TEXT_CSS)
                    if extra_css:
                        page.add_style_tag(content=extra_css)
                        page.evaluate("document.fonts.ready")
                    if prepare_js:
                        page.evaluate(prepare_js)
                    if snap_selector:
                        page.evaluate(_SNAP_JS, snap_selector)
                    page.locator("#receipt").screenshot(path=str(out_png))
                    if measure_selector:
                        boxes = page.evaluate(_MEASURE_JS, measure_selector)
                    if out_mhtml:
                        out_mhtml.write_bytes(snapshot_mhtml(page))
                finally:
                    browser.close()
        except Exception as e:
            msg = str(e).lower()
            if "executable" in msg or "browserType.launch" in str(e):
                raise RuntimeError(
                    "Playwright Chromium is not installed. Run: uv run playwright install chromium"
                ) from e
            raise
    return url, boxes
