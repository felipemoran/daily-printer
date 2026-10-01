import importlib.util
import sys
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location("font_metrics", ROOT / "src" / "scripts" / "experiments" / "font_metrics.py")
font_metrics = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(font_metrics)


class StemWidthTest(unittest.TestCase):
    def test_median_of_black_runs_on_the_row(self):
        row = Image.new("L", (20, 1), 255)
        for x in (1, 2, 6, 7, 11, 12, 13):  # runs of 2, 2, 3
            row.putpixel((x, 0), 0)
        self.assertEqual(font_metrics.stem_width(row, 0), 2)

    def test_run_touching_the_right_edge_counts(self):
        row = Image.new("L", (5, 1), 255)
        for x in (3, 4):
            row.putpixel((x, 0), 0)
        self.assertEqual(font_metrics.stem_width(row, 0), 2)

    def test_blank_row_is_zero(self):
        self.assertEqual(font_metrics.stem_width(Image.new("L", (5, 1), 255), 0), 0)


if __name__ == "__main__":
    unittest.main()
