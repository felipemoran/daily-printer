import io
import sys
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from photo_dither import _KERNELS, METHODS, _bayer_matrix, dither, erode_bottom_edges, prepare  # noqa: E402


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

    def test_floyd_steinberg_golden_2x2(self):
        # Hand-computed for a flat 2x2 at value 100. The serpentine pass runs
        # row 1 right-to-left, so the mirrored 7/16 tap flips pixel (0, 1).
        flat = Image.new("L", (2, 2), 100)
        plain = dither(flat, "floyd-steinberg", serpentine=False).convert("L").tobytes()
        snake = dither(flat, "floyd-steinberg", serpentine=True).convert("L").tobytes()
        self.assertEqual(list(plain), [0, 255, 0, 0])
        self.assertEqual(list(snake), [0, 255, 255, 0])

    def test_kernels_diffuse_full_error_except_atkinson(self):
        for name, (divisor, taps) in _KERNELS.items():
            with self.subTest(kernel=name):
                expected = 6 if name == "atkinson" else divisor
                self.assertEqual(sum(weight for _, _, weight in taps), expected)

    def test_bayer_matrix_is_the_standard_4x4(self):
        self.assertEqual(
            _bayer_matrix(4),
            [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]],
        )

    def test_unknown_method_names_the_choices(self):
        with self.assertRaisesRegex(ValueError, "atkinson"):
            dither(Image.new("L", (4, 4)), "nope")


def _erode_by_hand(bitmap: Image.Image, min_run: int) -> Image.Image:
    source = bitmap.convert("L")
    width, height = source.size
    pixels = source.load()
    black = lambda x, y: 0 <= y < height and pixels[x, y] == 0  # noqa: E731
    out = source.copy()
    written = out.load()
    for y in range(height):
        for x in range(width):
            if all(black(x, y - k) for k in range(min_run)) and not black(x, y + 1):
                written[x, y] = 255
    return out


class ErodeBottomEdgesTest(unittest.TestCase):
    def _column(self, image, x, rows):
        return [image.getpixel((x, y)) for y in rows]

    def test_min_run_spares_short_runs_and_trims_tall_ones(self):
        image = Image.new("L", (5, 8), 255)
        for y in (1, 2):
            image.putpixel((1, y), 0)  # 2-dot run: dither-like
        for y in (1, 2, 3, 4):
            image.putpixel((3, y), 0)  # 4-dot run: stem-like
        two = erode_bottom_edges(image, min_run=2).convert("L")
        three = erode_bottom_edges(image, min_run=3).convert("L")
        self.assertEqual(self._column(two, 1, (1, 2)), [0, 255])
        self.assertEqual(self._column(three, 1, (1, 2)), [0, 0])
        self.assertEqual(self._column(three, 3, (1, 2, 3, 4)), [0, 0, 0, 255])

    def test_run_touching_the_bottom_edge_is_trimmed(self):
        image = Image.new("L", (1, 4), 255)
        for y in (1, 2, 3):
            image.putpixel((0, y), 0)
        out = erode_bottom_edges(image, min_run=3).convert("L")
        self.assertEqual(self._column(out, 0, range(4)), [255, 0, 0, 255])

    def test_matches_reference_rule(self):
        gray = Image.linear_gradient("L").resize((96, 64))
        edge_band = Image.new("1", (96, 64), 1)
        edge_band.paste(0, (0, 10, 96, 20))
        for source in (dither(gray, "atkinson"), edge_band):
            for min_run in (2, 3, 4):
                with self.subTest(size=source.size, min_run=min_run):
                    expected = _erode_by_hand(source, min_run).tobytes()
                    self.assertEqual(erode_bottom_edges(source, min_run=min_run).convert("L").tobytes(), expected)

    def test_rejects_min_run_below_two(self):
        with self.assertRaises(ValueError):
            erode_bottom_edges(Image.new("1", (4, 4)), min_run=1)


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

    def test_transparent_palette_background_becomes_paper_white(self):
        source = Image.new("PA", (100, 100), (0, 0))
        out = prepare(source, width=50, contrast_cutoff=0, sharpen=0)
        self.assertEqual(out.getextrema(), (255, 255))

    def test_16bit_grayscale_is_scaled_not_clipped(self):
        gradient = Image.linear_gradient("L").point(lambda value: value * 257, mode="I").convert("I;16")
        out = prepare(gradient, width=64, contrast_cutoff=0, sharpen=0, gamma=1.0)
        low, high = out.getextrema()
        self.assertLess(low, 10)
        self.assertGreater(high, 245)
        self.assertAlmostEqual(sum(out.tobytes()) / (64 * 64), 127.5, delta=10)

    def test_gamma_above_one_lightens_midtones(self):
        gradient = Image.linear_gradient("L").convert("RGB")
        neutral = prepare(gradient, width=64, gamma=1.0, sharpen=0, contrast_cutoff=0)
        lifted = prepare(gradient, width=64, gamma=1.6, sharpen=0, contrast_cutoff=0)
        mean = lambda image: sum(image.tobytes()) / (image.width * image.height)  # noqa: E731
        self.assertGreater(mean(lifted), mean(neutral) + 20)


if __name__ == "__main__":
    unittest.main()
