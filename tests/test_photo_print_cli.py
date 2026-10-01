import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

SCRIPT = Path(__file__).resolve().parents[1] / "src" / "scripts" / "photo_print.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False)


class PhotoPrintCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.photo = self.tmp / "friends.jpg"
        Image.linear_gradient("L").convert("RGB").resize((600, 800)).save(self.photo)
        self.out = self.tmp / "out"

    def test_compare_writes_sheet_without_touching_printer(self):
        result = _run(str(self.photo), "--compare", "--artifact-dir", str(self.out))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.out / "friends-compare.png").is_file())

    def test_test_strip_no_print_writes_one_band_per_method(self):
        result = _run(str(self.photo), "--test-strip", "--no-print", "--artifact-dir", str(self.out))
        self.assertEqual(result.returncode, 0, result.stderr)
        bands = sorted(self.out.glob("friends-strip-*.png"))
        self.assertEqual(len(bands), 6)
        with Image.open(bands[0]) as band:
            self.assertEqual(band.size, (384, 128))

    def test_single_preview_is_print_width_1bit(self):
        result = _run(str(self.photo), "--method", "bayer", "--no-print", "--artifact-dir", str(self.out))
        self.assertEqual(result.returncode, 0, result.stderr)
        with Image.open(self.out / "friends-bayer.png") as preview:
            self.assertEqual((preview.mode, preview.size), ("1", (384, 512)))

    def test_rejects_invalid_gamma(self):
        for value in ("0", "-1", "nan", "inf"):
            with self.subTest(gamma=value):
                result = _run(str(self.photo), "--gamma", value, "--no-print")
                self.assertEqual(result.returncode, 2)
                self.assertIn("--gamma must be a finite number greater than 0", result.stderr)

    def test_truncated_jpeg_reports_error_without_traceback(self):
        broken = self.tmp / "broken.jpg"
        broken.write_bytes(self.photo.read_bytes()[:500])
        result = _run(str(broken), "--no-print", "--artifact-dir", str(self.out))
        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR: not a readable image", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_heic_gets_a_conversion_hint(self):
        fake = self.tmp / "IMG_0001.HEIC"
        fake.write_bytes(b"not really heic")
        result = _run(str(fake), "--no-print", "--artifact-dir", str(self.out))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sips -s format jpeg", result.stderr)


if __name__ == "__main__":
    unittest.main()
