"""End-to-end: a 1-bit bitmap must survive Chromium render + threshold bit for bit."""

import importlib.util
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from raster_capture import capture_receipt  # noqa: E402
from receipt_image import prepare_for_escpos  # noqa: E402

_spec = importlib.util.spec_from_file_location("page_print", ROOT / "src" / "scripts" / "page_print.py")
page_print = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(page_print)

# 17px * 1.35 line height puts the image at a fractional y.
PAGE = """<!doctype html><html><head><style>
html, body { margin: 0; }
#receipt { width: 384px; box-sizing: border-box; padding: 0 9px; font: 17px/1.35 monospace; }
img { display: block; image-rendering: pixelated; }
</style></head><body><main id="receipt">
<p>one</p><p>two</p><img data-photo src="photo.png"><p>after</p>
</main></body></html>"""


def _noise(width: int, height: int) -> Image.Image:
    rng = random.Random(42)
    image = Image.new("1", (width, height))
    image.putdata([rng.choice((0, 255)) for _ in range(width * height)])
    return image


class PageAlignmentTest(unittest.TestCase):
    def setUp(self):
        self.site = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.site)
        (self.site / "index.html").write_text(PAGE)
        self.bitmap = _noise(366, 120)
        self.bitmap.save(self.site / "photo.png")

    def _capture(self, snap: bool):
        shot = self.site / "shot.png"
        _, boxes = capture_receipt(
            self.site,
            out_png=shot,
            measure_selector="img[data-photo]",
            snap_selector="img[data-photo]" if snap else None,
        )
        return shot, boxes[0]

    def test_text_above_leaves_image_off_the_pixel_grid(self):
        _, box = self._capture(snap=False)
        self.assertNotEqual(box["y"], int(box["y"]))

    def test_snapped_bitmap_survives_render_and_threshold_exactly(self):
        shot, box = self._capture(snap=True)
        page = prepare_for_escpos(shot, target_width=384, dither=False)
        self.assertEqual(page_print.alignment_problems(page.width, box, self.bitmap.size), [])
        self.assertEqual(page_print.mismatched_pixels(page, box, self.bitmap), 0)


class PagePrintCliTest(unittest.TestCase):
    def test_photo_mode_on_sample_page_is_pixel_exact(self):
        out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, out)
        photo = out / "photo.jpg"
        Image.linear_gradient("L").convert("RGB").resize((500, 400)).save(photo)
        result = subprocess.run(
            [sys.executable, str(ROOT / "src" / "scripts" / "page_print.py"),
             "--photo", str(photo), "--mode", "photo", "--no-print", "--artifact-dir", str(out / "run")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("render + threshold: 0 of", result.stdout)
        self.assertNotIn("WARNING", result.stderr)


if __name__ == "__main__":
    unittest.main()
