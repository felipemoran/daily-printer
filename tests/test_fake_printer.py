import sys
import tempfile
import unittest
from pathlib import Path

from escpos.printer import Dummy
from PIL import Image, ImageChops, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fake_printer import FakePrinter, decode  # noqa: E402
from printer import PRINT_WIDTH_DOTS  # noqa: E402


def _escpos_bytes(image: Image.Image) -> bytes:
    printer = Dummy()
    printer.profile.profile_data["media"]["width"]["pixels"] = PRINT_WIDTH_DOTS
    printer.hw("INIT")
    printer.image(image, center=False)
    printer.ln(3)
    return printer.output


def _pattern(height: int) -> Image.Image:
    image = Image.new("1", (PRINT_WIDTH_DOTS, height), 1)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 50, 20), fill=0)
    for y in range(30, height, 7):
        draw.line((y % PRINT_WIDTH_DOTS, y, PRINT_WIDTH_DOTS - 1, y), fill=0)
    return image


class DecodeTest(unittest.TestCase):
    def assertSameImage(self, expected: Image.Image, actual: Image.Image) -> None:
        self.assertEqual(expected.size, actual.size)
        self.assertIsNone(ImageChops.difference(expected.convert("L"), actual.convert("L")).getbbox())

    def test_round_trips_python_escpos_output(self):
        image = _pattern(200)
        self.assertSameImage(image, decode(_escpos_bytes(image)))

    def test_stacks_the_fragments_of_a_tall_image(self):
        image = _pattern(2500)  # python-escpos sends 960-row fragments
        self.assertGreater(_escpos_bytes(image).count(b"\x1dv0"), 1)
        self.assertSameImage(image, decode(_escpos_bytes(image)))

    def test_rejects_data_without_a_raster(self):
        with self.assertRaisesRegex(ValueError, "no GS v 0"):
            decode(b"\x1b@hello\n")

    def test_rejects_cut_short_data(self):
        with self.assertRaisesRegex(ValueError, "cut short"):
            decode(_escpos_bytes(_pattern(50))[:-200])


class FakePrinterTest(unittest.TestCase):
    def test_writes_png_and_raw_bytes_from_chunks(self):
        data = _escpos_bytes(_pattern(120))
        with tempfile.TemporaryDirectory() as tmp:
            printer = FakePrinter(Path(tmp))
            for i in range(0, len(data), 4096):
                printer.write(data[i:i + 4096])
            png = printer.finish("job-1")
            self.assertEqual((Path(tmp) / "job-1.bin").read_bytes(), data)
            with Image.open(png) as image:
                self.assertEqual(image.size, (PRINT_WIDTH_DOTS, 120))


if __name__ == "__main__":
    unittest.main()
