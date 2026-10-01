"""
Print one bitmap strip under head-heat variants, to study the dark smear below strokes.

  --test esc7     default heat, then ESC 7 heat time 50 and 30, then cooling interval 200
  --test feed     full speed, then the same bytes paced over USB at 2000, 800, 400 B/s
  --test erosion  full speed without and with bottom-edge erosion

2026-10 results on the MPT-II: the firmware ignores ESC 7; slow feeding cuts
smear but fades solid blacks and can band; erosion (run >= 3) won. Power-cycle
the printer after --test esc7: the settings may persist until power-off.

Example:
  uv run src/scripts/experiments/heat_tests.py artifacts/spec/page-atkinson.png --rows 243,470 --test feed
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from escpos.printer import Dummy
from PIL import Image

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from photo_dither import erode_bottom_edges  # noqa: E402
from printer import _apply_profile, open_printer  # noqa: E402


def _esc7(dots: int, heat_time: int, interval: int) -> bytes:
    return b"\x1b\x37" + bytes([dots, heat_time, interval])


def _job(label: str, image: Image.Image, prefix: bytes = b"") -> bytes:
    d = Dummy()
    _apply_profile(d)
    d._raw(prefix)
    d.text(f"{label}\n")
    d.image(image, center=False)
    d.ln(1)
    return d.output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("image", type=Path, help="1-bit (or greyscale) PNG at print width")
    parser.add_argument("--rows", default=None, help="top,bottom rows to print (default: all)")
    parser.add_argument("--test", choices=("esc7", "feed", "erosion"), required=True)
    args = parser.parse_args()

    image = Image.open(args.image).convert("L")
    if args.rows:
        top, bottom = map(int, args.rows.split(","))
        image = image.crop((0, top, image.width, bottom))
    strip = image.convert("1", dither=Image.Dither.NONE)
    eroded = erode_bottom_edges(strip, min_run=3)

    jobs: list[tuple[str, bytes, float | None]] = {
        "esc7": [
            ("default heat", _job("default heat", strip), None),
            ("ESC 7 heat time 50", _job("ESC 7 heat time 50", strip, _esc7(7, 50, 2)), None),
            ("ESC 7 heat time 30", _job("ESC 7 heat time 30", strip, _esc7(7, 30, 2)), None),
            ("ESC 7 cool interval 200", _job("ESC 7 cool interval 200", strip, _esc7(7, 80, 200)), None),
        ],
        "feed": [(f"{name}", _job(name, strip), rate) for name, rate in
                 [("full speed", None), ("2000 B/s", 2000), ("800 B/s", 800), ("400 B/s", 400)]],
        "erosion": [
            ("full speed", _job("full speed", strip), None),
            ("full speed + erosion run>=3", _job("full speed + erosion run>=3", eroded), None),
        ],
    }[args.test]

    with open_printer() as p:
        for label, data, rate in jobs:
            start = time.monotonic()
            if rate is None:
                p._raw(data)
            else:
                for i in range(0, len(data), 48):
                    p._raw(data[i:i + 48])
                    delay = start + (i + 48) / rate - time.monotonic()
                    if delay > 0:
                        time.sleep(delay)
            print(f"{label}: {len(data)} bytes in {time.monotonic() - start:.1f}s", flush=True)
        p.ln(2)


if __name__ == "__main__":
    main()
