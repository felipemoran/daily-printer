import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from print_profile import DEFAULT_PROFILE, LEGACY_PROFILE, capture_options, load_gray, to_bitmap  # noqa: E402
from receipt_image import prepare_for_escpos  # noqa: E402


def _screenshot(path: Path) -> Path:
    image = Image.new("RGBA", (384, 120), (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 383, 30), fill=(0, 0, 0, 255))
    for x in range(384):
        draw.line((x, 40, x, 80), fill=(x * 255 // 383,) * 3 + (255,))
    draw.text((10, 90), "receipt text", fill=(0, 0, 0, 255))
    image.save(path)
    return path


class ProfileTest(unittest.TestCase):
    def test_defaults_are_the_paper_tested_picks(self):
        self.assertEqual(
            (DEFAULT_PROFILE.dither, DEFAULT_PROFILE.method, DEFAULT_PROFILE.aliased_text,
             DEFAULT_PROFILE.light_text_halo, DEFAULT_PROFILE.weight, DEFAULT_PROFILE.erode_min_run),
            ("page", "atkinson", True, True, "auto", 3),
        )

    def test_legacy_reproduces_the_old_threshold_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            shot = _screenshot(Path(tmp) / "shot.png")
            legacy = to_bitmap(load_gray(shot), LEGACY_PROFILE)
            old = prepare_for_escpos(shot, target_width=384, dither=False)
            self.assertEqual(legacy.convert("L").tobytes(), old.convert("L").tobytes())

    def test_legacy_capture_adds_nothing(self):
        self.assertEqual(
            capture_options(LEGACY_PROFILE),
            {"aliased_text": False, "extra_css": None, "prepare_js": None},
        )

    def test_default_capture_snaps_sizes_sets_weights_and_halo(self):
        script = capture_options(DEFAULT_PROFILE)["prepare_js"]
        for marker in ("Math.round(size * SCALE)", "fontWeight", "textShadow"):
            self.assertIn(marker, script)


if __name__ == "__main__":
    unittest.main()
