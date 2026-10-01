import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from print_profile import DEFAULT_PROFILE, LEGACY_PROFILE, capture_options, describe, load_gray, to_bitmap  # noqa: E402


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

    def test_legacy_thresholds_at_200_without_erosion(self):
        with tempfile.TemporaryDirectory() as tmp:
            gray = load_gray(_screenshot(Path(tmp) / "shot.png"))
            legacy = to_bitmap(gray, LEGACY_PROFILE).convert("L")
            expected = [255 if value > 200 else 0 for value in gray.tobytes()]
            self.assertEqual(list(legacy.tobytes()), expected)

    def test_legacy_capture_forces_anti_aliasing_and_nothing_else(self):
        options = capture_options(LEGACY_PROFILE)
        self.assertEqual((options["aliased_text"], options["prepare_js"]), (False, None))
        self.assertIn("-webkit-font-smoothing: antialiased", options["extra_css"])

    def test_page_gamma_is_labelled_only_when_applied(self):
        self.assertIn("page gamma", describe(DEFAULT_PROFILE.with_(page_gamma=0.8)))
        self.assertNotIn("page gamma", describe(DEFAULT_PROFILE.with_(page_gamma=0.8, dither="none")))

    def test_font_names_are_escaped_in_css(self):
        css = capture_options(DEFAULT_PROFILE.with_(font="O'Font"))["extra_css"]
        self.assertIn("'O\\'Font'", css)

    def test_default_capture_snaps_sizes_sets_weights_and_halo(self):
        script = capture_options(DEFAULT_PROFILE)["prepare_js"]
        for marker in ("Math.round(size * SCALE)", "fontWeight", "textShadow"):
            self.assertIn(marker, script)


if __name__ == "__main__":
    unittest.main()
