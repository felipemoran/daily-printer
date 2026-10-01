import io
import sys
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from photo_dither import METHODS, dither, prepare  # noqa: E402


def _white_fraction(image: Image.Image) -> float:
    data = image.convert("L").tobytes()
    return sum(1 for value in data if value) / len(data)


class DitherTest(unittest.TestCase):
    def test_every_method_returns_same_size_1bit(self):
        gray = Image.linear_gradient("L").resize((64, 48))
        for method in METHODS:
            with self.subTest(method=method):
                out = dither(gray, method)
                self.assertEqual(out.mode, "1")
                self.assertEqual(out.size, (64, 48))

    def test_paper_white_and_solid_black_stay_clean(self):
        for method in METHODS:
            with self.subTest(method=method):
                self.assertEqual(_white_fraction(dither(Image.new("L", (40, 40), 255), method)), 1.0)
                self.assertEqual(_white_fraction(dither(Image.new("L", (40, 40), 0), method)), 0.0)

    def test_halftone_methods_preserve_mid_gray(self):
        flat = Image.new("L", (96, 96), 128)
        for method in ("floyd-steinberg", "atkinson", "jarvis", "stucki", "bayer"):
            with self.subTest(method=method):
                self.assertAlmostEqual(_white_fraction(dither(flat, method)), 0.5, delta=0.05)

    def test_light_gray_prints_lighter_than_dark_gray(self):
        for method in ("floyd-steinberg", "atkinson", "jarvis", "stucki", "bayer"):
            with self.subTest(method=method):
                light = _white_fraction(dither(Image.new("L", (64, 64), 190), method))
                dark = _white_fraction(dither(Image.new("L", (64, 64), 60), method))
                self.assertGreater(light, dark + 0.3)

    def test_unknown_method_names_the_choices(self):
        with self.assertRaisesRegex(ValueError, "atkinson"):
            dither(Image.new("L", (4, 4)), "nope")


class PrepareTest(unittest.TestCase):
    def test_scales_to_print_width_keeping_aspect(self):
        out = prepare(Image.new("RGB", (800, 600), "gray"), width=384)
        self.assertEqual(out.mode, "L")
        self.assertEqual(out.size, (384, 288))

    def test_applies_exif_rotation_from_phone_photos(self):
        source = Image.new("RGB", (800, 400), "gray")
        exif = source.getexif()
        exif[0x0112] = 6  # Orientation: rotate 90 CW
        buffer = io.BytesIO()
        source.save(buffer, format="JPEG", exif=exif)
        buffer.seek(0)

        out = prepare(Image.open(buffer), width=384)
        self.assertEqual(out.size, (384, 768))

    def test_transparent_background_becomes_paper_white(self):
        out = prepare(Image.new("RGBA", (100, 100), (0, 0, 0, 0)), width=50, contrast_cutoff=0, sharpen=0)
        self.assertEqual(out.getextrema(), (255, 255))

    def test_gamma_above_one_lightens_midtones(self):
        gradient = Image.linear_gradient("L").convert("RGB")
        neutral = prepare(gradient, width=64, gamma=1.0, sharpen=0, contrast_cutoff=0)
        lifted = prepare(gradient, width=64, gamma=1.6, sharpen=0, contrast_cutoff=0)
        mean = lambda image: sum(image.tobytes()) / (image.width * image.height)  # noqa: E731
        self.assertGreater(mean(lifted), mean(neutral) + 20)


if __name__ == "__main__":
    unittest.main()
