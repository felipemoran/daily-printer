"""Serve ``web/dist`` over loopback and capture the ``#receipt`` node as PNG with Playwright."""

from __future__ import annotations

import contextlib
import socket
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright


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


def screenshot_receipt_dist(
    dist_dir: Path,
    *,
    host: str = "127.0.0.1",
    index_path: str = "/index.html",
    out_png: Path,
    device_scale_factor: float = 1.0,
) -> str:
    """Serve ``dist_dir``, open ``index_path``, write ``out_png``. Returns page URL."""
    dist_dir = dist_dir.resolve()
    out_png.parent.mkdir(parents=True, exist_ok=True)

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
                    page.locator("#receipt").screenshot(path=str(out_png))
                finally:
                    browser.close()
        except Exception as e:
            msg = str(e).lower()
            if "executable" in msg or "browserType.launch" in str(e):
                raise RuntimeError(
                    "Playwright Chromium is not installed. Run: uv run playwright install chromium"
                ) from e
            raise
    return url
