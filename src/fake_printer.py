"""Stand-in for a receipt printer: saves what the paper would show as a PNG."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

_RASTER = b"\x1dv0"  # GS v 0
_HEADER_SIZE = len(_RASTER) + 5  # m xL xH yL yH


def decode(data: bytes) -> Image.Image:
    """Stack every GS v 0 raster in ``data``, top to bottom. Other commands are skipped."""
    blocks = []
    start = data.find(_RASTER)
    while start != -1:
        header = data[start + len(_RASTER):start + _HEADER_SIZE]
        if len(header) < 5:
            raise ValueError("GS v 0 header is cut short")
        mode, xl, xh, yl, yh = header
        if mode != 0:
            raise ValueError(f"GS v 0 mode {mode} is not supported; only 0 (normal)")
        width_bytes, height = xl + xh * 256, yl + yh * 256
        end = start + _HEADER_SIZE + width_bytes * height
        if end > len(data):
            raise ValueError("GS v 0 pixel data is cut short")
        # ESC/POS uses 1 for black; Pillow's "1;I" raw mode reads that bit order.
        blocks.append(Image.frombytes("1", (width_bytes * 8, height), data[start + _HEADER_SIZE:end], "raw", "1;I"))
        start = data.find(_RASTER, end)
    if not blocks:
        raise ValueError("no GS v 0 raster image in the data")

    page = Image.new("1", (max(b.width for b in blocks), sum(b.height for b in blocks)), 1)
    top = 0
    for block in blocks:
        page.paste(block, (0, top))
        top += block.height
    return page


class FakePrinter:
    """Collects one job's bytes; ``finish`` writes ``<out_dir>/<name>.png`` and the raw ``.bin``."""

    def __init__(self, out_dir: Path) -> None:
        self.out_dir = out_dir
        self._buffer = bytearray()

    def write(self, chunk: bytes) -> None:
        self._buffer += chunk

    def finish(self, name: str) -> Path:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        data = bytes(self._buffer)
        self._buffer.clear()
        (self.out_dir / f"{name}.bin").write_bytes(data)
        png = self.out_dir / f"{name}.png"
        decode(data).save(png)
        return png
