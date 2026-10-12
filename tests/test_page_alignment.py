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

import print_profile  # noqa: E402
from raster_capture import capture_receipt  # noqa: E402

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
        page = print_profile.threshold(print_profile.load_gray(shot))
        self.assertEqual(page_print.alignment_problems(page.width, box, self.bitmap.size), [])
        self.assertEqual(page_print.mismatched_pixels(page, box, self.bitmap), 0)


class AliasedTextTest(unittest.TestCase):
    def test_aliased_text_renders_only_black_and_white(self):
        site = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, site)
        (site / "index.html").write_text(
            '<main id="receipt" style="width:384px;font:19px serif">Anti-aliasing would add greys here.</main>'
        )
        levels = {}
        for aliased in (False, True):
            capture_receipt(site, out_png=site / "shot.png", aliased_text=aliased)
            with Image.open(site / "shot.png") as shot:
                levels[aliased] = len(set(shot.convert("L").tobytes()))
        self.assertGreater(levels[False], 2)
        self.assertEqual(levels[True], 2)


class LightTextHaloTest(unittest.TestCase):
    def test_outlines_light_text_only(self):
        site = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, site)
        (site / "index.html").write_text(
            '<main id="receipt" style="width:384px">'
            '<p id="light" style="color:#fff;background:#888">light</p>'
            '<p id="dark" style="color:#111">dark</p></main>'
        )
        probe = "() => ['light', 'dark'].map((id) => document.getElementById(id).style.textShadow)"
        from playwright.sync_api import sync_playwright
        from raster_capture import static_server
        with static_server(site) as port, sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{port}/index.html")
            page.evaluate(print_profile.text_effects_js(halo=True, faux_bold=False))
            light, dark = page.evaluate(probe)
            browser.close()
        self.assertIn("rgb(0, 0, 0)", light)
        self.assertEqual(dark, "")

    def test_dark_text_nested_in_light_text_gets_no_halo(self):
        site = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, site)
        (site / "index.html").write_text(
            '<main id="receipt" style="width:384px;background:#888">'
            '<p id="light" style="color:oklch(0.98 0 0)">Light <b id="dark" style="color:#000">dark</b>'
            ' <i id="own" style="color:#000;text-shadow:2px 2px 0 red">own</i></p></main>'
        )
        from playwright.sync_api import sync_playwright
        from raster_capture import static_server
        with static_server(site) as port, sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{port}/index.html")
            page.evaluate(print_profile.text_effects_js(halo=True, faux_bold=False))
            light, dark, own = page.evaluate(
                "() => ['light', 'dark', 'own'].map((id) => getComputedStyle(document.getElementById(id)).textShadow)"
            )
            browser.close()
        self.assertIn("rgb(0, 0, 0)", light)
        self.assertEqual(dark, "none")
        self.assertIn("rgb(255, 0, 0)", own)


class AutoWeightTest(unittest.TestCase):
    def test_small_text_goes_bold_and_large_text_regular(self):
        site = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, site)
        (site / "index.html").write_text(
            '<main id="receipt" style="width:384px">'
            '<p id="small" style="font-size:16px">small</p><p id="large" style="font-size:24px">large</p></main>'
        )
        from playwright.sync_api import sync_playwright
        from raster_capture import static_server
        with static_server(site) as port, sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{port}/index.html")
            page.evaluate(print_profile.auto_weight_js())
            weights = page.evaluate(
                "() => ['small', 'large'].map((id) => getComputedStyle(document.getElementById(id)).fontWeight)"
            )
            browser.close()
        self.assertEqual(weights, ["700", "400"])

    def test_thermal_pages_keep_their_own_weights(self):
        site = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, site)
        (site / "index.html").write_text(
            '<div id="receipt" class="rp-paper" style="width:384px">'
            '<p id="display" style="font-size:92px;font-weight:900">OPS</p>'
            '<p id="body" style="font-size:16px;font-weight:500">body</p></div>'
        )
        from playwright.sync_api import sync_playwright
        from raster_capture import static_server
        with static_server(site) as port, sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{port}/index.html")
            page.evaluate(print_profile.auto_weight_js())
            weights = page.evaluate(
                "() => ['display', 'body'].map((id) => getComputedStyle(document.getElementById(id)).fontWeight)"
            )
            browser.close()
        self.assertEqual(weights, ["900", "500"])


class LegacyAntiAliasingTest(unittest.TestCase):
    def test_legacy_restores_anti_aliasing_on_pages_that_turn_it_off(self):
        site = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, site)
        (site / "index.html").write_text(
            '<main id="receipt" style="width:384px;font:19px serif;-webkit-font-smoothing:none">'
            "Greys only with anti-aliasing.</main>"
        )
        levels = {}
        for name, profile in (("default", print_profile.DEFAULT_PROFILE), ("legacy", print_profile.LEGACY_PROFILE)):
            capture_receipt(site, out_png=site / "shot.png", **print_profile.capture_options(profile))
            with Image.open(site / "shot.png") as shot:
                levels[name] = len(set(shot.convert("L").tobytes()))
        self.assertEqual(levels["default"], 2)
        self.assertGreater(levels["legacy"], 2)


class PagePrintCliTest(unittest.TestCase):
    def test_photo_mode_on_sample_page_is_pixel_exact(self):
        out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, out)
        photo = out / "photo.jpg"
        Image.linear_gradient("L").convert("RGB").resize((500, 400)).save(photo)
        result = subprocess.run(
            [sys.executable, str(ROOT / "src" / "scripts" / "page_print.py"),
             "--photo", str(photo), "--dither", "photo", "--no-print", "--artifact-dir", str(out / "run")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("render + threshold: 0 of", result.stdout)
        self.assertNotIn("WARNING", result.stderr)


class PagePrintNoPhotoTest(unittest.TestCase):
    def test_ui_page_renders_with_and_without_dithering(self):
        out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, out)
        for mode, artifact in (("page", "page-atkinson.png"), ("none", "threshold.png")):
            with self.subTest(dither=mode):
                result = subprocess.run(
                    [sys.executable, str(ROOT / "src" / "scripts" / "page_print.py"),
                     "--page", str(ROOT / "samples" / "ui-elements"), "--dither", mode,
                     "--no-print", "--artifact-dir", str(out / mode)],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                with Image.open(out / mode / artifact) as image:
                    self.assertEqual((image.mode, image.width), ("1", 384))

    def test_font_override_changes_the_render(self):
        out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, out)
        renders = {}
        for font in (None, "Verdana"):
            args = ["--font", font] if font else []
            result = subprocess.run(
                [sys.executable, str(ROOT / "src" / "scripts" / "page_print.py"),
                 "--page", str(ROOT / "samples" / "ui-elements"), "--dither", "none", *args,
                 "--no-print", "--artifact-dir", str(out / str(font))],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            renders[font] = (out / str(font) / "page.png").read_bytes()
        self.assertNotEqual(renders[None], renders["Verdana"])

    def test_font_scale_makes_the_page_taller(self):
        out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, out)
        heights = {}
        for scale in ("1.0", "1.2"):
            result = subprocess.run(
                [sys.executable, str(ROOT / "src" / "scripts" / "page_print.py"),
                 "--page", str(ROOT / "samples" / "photo-page"), "--dither", "none", "--font-scale", scale,
                 "--no-print", "--artifact-dir", str(out / scale)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with Image.open(out / scale / "page.png") as page:
                heights[scale] = page.height
        self.assertGreater(heights["1.2"], heights["1.0"] * 1.05)

    def test_photo_dither_requires_a_photo(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "src" / "scripts" / "page_print.py"), "--dither", "photo", "--no-print"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--dither photo needs --photo", result.stderr)


if __name__ == "__main__":
    unittest.main()
