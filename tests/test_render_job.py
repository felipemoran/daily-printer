import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from escpos.constants import HW_INIT
from PIL import Image, ImageChops, ImageDraw, ImageFile
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, sync_playwright

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

import render_job  # noqa: E402
from fake_printer import decode  # noqa: E402
from printer import PRINT_WIDTH_DOTS  # noqa: E402
from render_job import MAX_HEIGHT_DOTS, MAX_SOURCE_PIXELS, TEXT_FEED, RenderError, escpos_from_png, render  # noqa: E402
from ticket_templates import MAX_DEPTH, open_render_page, render_template, render_text  # noqa: E402

SAMPLE_PAYLOAD = json.loads((_ROOT / "samples" / "receipt-sample.json").read_text(encoding="utf-8"))
SAMPLE_TASK = next(block for block in SAMPLE_PAYLOAD["blocks"] if block["type"] == "task")
TEMPLATE_SAMPLES = sorted((_ROOT / "samples" / "templates").glob("*.json"))
TICKET = json.loads((_ROOT / "samples" / "templates" / "ticket.json").read_text(encoding="utf-8"))
BUILD = json.loads((_ROOT / "samples" / "templates" / "build.json").read_text(encoding="utf-8"))
BUILD_PASSED = {**BUILD, "data": {**BUILD["data"], "status": "passed", "failures": []}}
# A Chromium launch plus a rejected render; far below the 30 s screenshot wait.
FAST_REJECT_SECONDS = 10


def _photo(size: tuple[int, int], mode: str, fmt: str, *, exif: Image.Exif | None = None) -> bytes:
    """A gradient with shapes and mid-tones, encoded as an upload would be."""
    width, height = size
    picture = Image.merge(
        "RGB",
        (
            Image.linear_gradient("L").resize(size),
            Image.linear_gradient("L").rotate(90).resize(size),
            Image.radial_gradient("L").resize(size),
        ),
    ).convert(mode)
    draw = ImageDraw.Draw(picture)
    draw.ellipse((width // 5, height // 5, width // 2, height // 2), fill="black" if mode != "RGBA" else (0, 0, 0, 255))
    draw.rectangle((width // 2, height // 2, width - 10, height - 10), fill="white" if mode != "RGBA" else (255, 255, 255, 0))
    out = io.BytesIO()
    picture.save(out, format=fmt, **({"exif": exif} if exif else {}))
    return out.getvalue()


def _nested(depth: int) -> dict:
    node: dict = {}
    for _ in range(depth):
        node = {"x": node}
    return node


def _rotated_exif() -> Image.Exif:
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90 degrees on display
    return exif


class RenderInvariants:
    rendered: render_job.Rendered

    def assertSameImage(self, expected: Image.Image, actual: Image.Image) -> None:
        self.assertEqual(expected.size, actual.size)
        self.assertIsNone(ImageChops.difference(expected.convert("L"), actual.convert("L")).getbbox())

    def test_bitmap_is_one_bit_at_print_width(self):
        self.assertEqual(self.rendered.bitmap.mode, "1")
        self.assertEqual(self.rendered.width, PRINT_WIDTH_DOTS)
        self.assertEqual(self.rendered.bitmap.size, (self.rendered.width, self.rendered.height))

    def test_png_size_equals_width_and_height(self):
        png = Image.open(io.BytesIO(self.rendered.png))
        self.assertEqual(png.size, (self.rendered.width, self.rendered.height))
        self.assertSameImage(self.rendered.bitmap, png)

    def test_escpos_prints_exactly_the_bitmap(self):
        self.assertSameImage(self.rendered.bitmap, decode(self.rendered.escpos))

    def test_reprint_from_png_prints_the_same_bitmap(self):
        self.assertSameImage(self.rendered.bitmap, decode(escpos_from_png(self.rendered.png)))

    def test_bitmap_has_both_ink_and_paper(self):
        self.assertEqual(self.rendered.bitmap.convert("L").getextrema(), (0, 255))

    def test_render_ms_is_recorded(self):
        self.assertGreaterEqual(self.rendered.render_ms, 0)


class ReceiptRenderTest(RenderInvariants, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rendered = render("receipt", payload=SAMPLE_PAYLOAD)

    def test_receipt_is_taller_than_one_line(self):
        self.assertGreater(self.rendered.height, 200)


class TicketTemplateRenderTest(RenderInvariants, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rendered = render("template", payload=TICKET)


class TextRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {"failed": BUILD, "passed": BUILD_PASSED}
        cls.rendered = {name: render("text", payload=payload) for name, payload in cls.cases.items()}
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = open_render_page(browser)
                cls.expected = {
                    name: (render_template(page, payload, max_height_dots=MAX_HEIGHT_DOTS), render_text(page, payload))
                    for name, payload in cls.cases.items()
                }
            finally:
                browser.close()

    def test_text_bytes_are_init_then_body_then_the_feed(self):
        for name, rendered in self.rendered.items():
            with self.subTest(name):
                self.assertTrue(rendered.escpos.startswith(HW_INIT))
                self.assertTrue(rendered.escpos.endswith(b"\x1b2" + TEXT_FEED))
                self.assertEqual(rendered.escpos, HW_INIT + self.expected[name][1] + TEXT_FEED)

    def test_text_bytes_hold_no_raster(self):
        for name, rendered in self.rendered.items():
            with self.subTest(name):
                self.assertNotIn(b"\x1dv0", rendered.escpos)

    def test_preview_png_equals_the_render_template_bitmap(self):
        for name, rendered in self.rendered.items():
            with self.subTest(name):
                bitmap = self.expected[name][0]
                png = Image.open(io.BytesIO(rendered.png))
                self.assertEqual((rendered.width, rendered.height), bitmap.size)
                self.assertEqual(png.size, bitmap.size)
                self.assertIsNone(ImageChops.difference(png.convert("L"), bitmap.convert("L")).getbbox())

    def test_the_two_statuses_print_different_bodies(self):
        self.assertNotEqual(self.rendered["failed"].escpos, self.rendered["passed"].escpos)

    def test_template_without_a_text_mode_is_a_render_error(self):
        with self.assertRaisesRegex(RenderError, '^template "ticket" has no text mode$'):
            render("text", payload=TICKET)


class TemplateSamplesTest(unittest.TestCase):
    def test_every_template_sample_prints_exactly_its_bitmap_at_print_width(self):
        self.assertGreater(len(TEMPLATE_SAMPLES), 1)
        for path in TEMPLATE_SAMPLES:
            with self.subTest(path.stem):
                rendered = render("template", payload=json.loads(path.read_text(encoding="utf-8")))
                self.assertEqual((rendered.bitmap.mode, rendered.width), ("1", PRINT_WIDTH_DOTS))
                self.assertGreater(rendered.height, 0)
                paper = decode(rendered.escpos)
                self.assertEqual(paper.size, rendered.bitmap.size)
                self.assertIsNone(ImageChops.difference(paper.convert("L"), rendered.bitmap.convert("L")).getbbox())


class TemplateRenderErrorTest(unittest.TestCase):
    def test_unknown_template_is_a_render_error_naming_it(self):
        with self.assertRaisesRegex(RenderError, 'unknown template "nope"'):
            render("template", payload={**TICKET, "template": "nope"})

    def test_invalid_field_is_a_render_error_naming_the_field_path(self):
        with self.assertRaisesRegex(RenderError, r"^data\.titel: unknown field$"):
            render("template", payload={**TICKET, "data": {**TICKET["data"], "titel": "typo"}})

    def test_payload_that_is_not_an_object_is_a_render_error(self):
        with self.assertRaisesRegex(RenderError, "^payload: expected object$"):
            render("template", payload=["not", "an", "object"])

    def test_render_taller_than_the_server_cap_is_a_render_error(self):
        # The ticket sample is far shorter than 4000 dots, so the test lowers the cap below it.
        with mock.patch.object(render_job, "MAX_HEIGHT_DOTS", 100):
            with self.assertRaisesRegex(RenderError, "cm long; the limit is 1.25 cm$"):
                render("template", payload=TICKET)

    def test_envelope_faults_are_render_errors_before_chromium_launches(self):
        cases = {
            "unknown template": ({**TICKET, "template": "nope"}, '^unknown template "nope"'),
            "70 KB payload": ({**TICKET, "data": {**TICKET["data"], "note": "x" * 70_000}},
                              r"^payload: \d+ bytes; the limit is 65536$"),
            "data not an object": ({**TICKET, "data": ["not", "a", "dict"]}, "^data: expected object$"),
            # 150 levels hang page.evaluate; 900 levels exhaust Python's stack in Playwright's serializer.
            **{f"nested {levels} deep": ({**TICKET, "data": {**TICKET["data"], "deep": _nested(levels)}},
                                          f"^payload: nested more than {MAX_DEPTH} levels deep$")
               for levels in (150, 900)},
        }
        for kind in ("template", "text"):
            for name, (payload, message) in cases.items():
                with self.subTest(kind=kind, case=name), mock.patch.object(render_job, "sync_playwright") as playwright:
                    with self.assertRaisesRegex(RenderError, message):
                        render(kind, payload=payload)
                    playwright.assert_not_called()

    def test_server_fault_from_render_template_stays_a_runtime_error(self):
        fault = RuntimeError("server fault: render.html has no renderTemplate; rebuild web/dist")
        with mock.patch.object(render_job, "render_template", side_effect=fault):
            with self.assertRaisesRegex(RuntimeError, "^server fault: "):
                render("template", payload=TICKET)


class JpegPhotoRenderTest(RenderInvariants, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rendered = render("image", image=_photo((1200, 900), "RGB", "JPEG"))

    def test_landscape_photo_keeps_its_aspect_ratio(self):
        self.assertEqual(self.rendered.height, round(900 * PRINT_WIDTH_DOTS / 1200))


class TransparentPngRenderTest(RenderInvariants, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rendered = render("image", image=_photo((200, 500), "RGBA", "PNG"))

    def test_small_portrait_is_scaled_up_to_print_width(self):
        self.assertEqual(self.rendered.height, round(500 * PRINT_WIDTH_DOTS / 200))


class HeightCapTest(unittest.TestCase):
    def test_image_just_over_the_cap_is_rejected_before_any_dithering(self):
        upload = _photo((768, 2 * MAX_HEIGHT_DOTS + 2), "RGB", "JPEG")
        with (
            mock.patch.object(ImageFile.ImageFile, "load") as load,
            mock.patch.object(render_job, "prepare") as prepare,
            mock.patch.object(render_job, "dither") as dither,
        ):
            with self.assertRaisesRegex(RenderError, "limit is 50 cm"):
                render("image", image=upload)
        load.assert_not_called()
        prepare.assert_not_called()
        dither.assert_not_called()

    def test_image_just_under_the_cap_renders(self):
        rendered = render("image", image=_photo((768, 2 * MAX_HEIGHT_DOTS - 2), "RGB", "JPEG"))
        self.assertEqual((rendered.width, rendered.height), (PRINT_WIDTH_DOTS, MAX_HEIGHT_DOTS - 1))

    def test_cap_applies_to_the_height_after_exif_rotation(self):
        upload = _photo((2 * MAX_HEIGHT_DOTS + 2, 768), "RGB", "JPEG", exif=_rotated_exif())
        with mock.patch.object(render_job, "dither") as dither:
            with self.assertRaises(RenderError):
                render("image", image=upload)
        dither.assert_not_called()

    def test_pixel_count_over_the_pillow_limit_is_a_render_error(self):
        upload = _photo((384, 300), "RGB", "PNG")
        # 115,200 pixels: between 1x and 2x of the limit, Pillow only warns.
        with mock.patch.object(Image, "MAX_IMAGE_PIXELS", 100_000), mock.patch.object(render_job, "dither") as dither:
            with self.assertRaisesRegex(RenderError, "pixels"):
                render("image", image=upload)
        dither.assert_not_called()

    def test_decompression_bomb_is_a_render_error(self):
        upload = _photo((384, 300), "RGB", "PNG")
        # Over 2x the limit, Pillow raises DecompressionBombError.
        with mock.patch.object(Image, "MAX_IMAGE_PIXELS", 10_000):
            with self.assertRaises(RenderError):
                render("image", image=upload)

    def test_source_over_the_pixel_cap_is_rejected_from_its_header_before_decoding(self):
        side = int(MAX_SOURCE_PIXELS ** 0.5) + 1
        out = io.BytesIO()
        Image.new("1", (side, side), 1).save(out, format="PNG")
        self.assertLess(len(out.getvalue()), 1_000_000)
        with mock.patch.object(ImageFile.ImageFile, "load") as load:
            with self.assertRaisesRegex(RenderError, f"limit is {MAX_SOURCE_PIXELS:,}"):
                render("image", image=out.getvalue())
        load.assert_not_called()

    def test_large_jpeg_is_decoded_near_print_width(self):
        cases = {"landscape": (_photo((4000, 3000), "RGB", "JPEG"), 0),
                 "rotated by EXIF": (_photo((4000, 3000), "RGB", "JPEG", exif=_rotated_exif()), 1)}
        for name, (upload, printed_side) in cases.items():
            with self.subTest(name), mock.patch.object(render_job, "prepare", wraps=render_job.prepare) as prepare:
                rendered = render("image", image=upload)
                decoded = prepare.call_args.args[0].size
                self.assertGreaterEqual(decoded[printed_side], PRINT_WIDTH_DOTS)
                self.assertLess(decoded[printed_side], 2 * PRINT_WIDTH_DOTS)
                self.assertEqual(rendered.width, PRINT_WIDTH_DOTS)

    def test_receipt_taller_than_the_cap_is_rejected_before_the_screenshot(self):
        long_payload = {**SAMPLE_PAYLOAD, "blocks": SAMPLE_PAYLOAD["blocks"] + [SAMPLE_TASK] * 2000}
        started = time.monotonic()
        with mock.patch.object(Locator, "screenshot") as screenshot:
            with self.assertRaisesRegex(RenderError, "limit is 50 cm"):
                render("receipt", payload=long_payload)
        screenshot.assert_not_called()
        self.assertLess(time.monotonic() - started, FAST_REJECT_SECONDS)


class LoadingStateTest(unittest.TestCase):
    LOADING_MARKUP = '<div id="receipt" class="receipt"><p class="muted">Loading\u2026</p></div>'

    def test_receipt_still_loading_at_capture_is_a_server_fault(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content(self.LOADING_MARKUP)
                with self.assertRaises(PlaywrightError) as caught:
                    page.evaluate(render_job._PROBE_JS)
            finally:
                browser.close()
        with mock.patch.object(render_job, "capture_receipt", side_effect=caught.exception):
            with self.assertRaisesRegex(PlaywrightError, "still loading") as raised:
                render("receipt", payload=SAMPLE_PAYLOAD)
        self.assertNotIsInstance(raised.exception, RenderError)


class UnrenderablePayloadTest(unittest.TestCase):
    """Payloads that crash the receipt app, which then has no #receipt to capture."""

    PAYLOADS = {
        "no blocks": {"schemaVersion": 2},
        "null block": {**SAMPLE_PAYLOAD, "blocks": [None]},
        "labels not a list": {**SAMPLE_PAYLOAD, "blocks": [{**SAMPLE_TASK, "labels": "x"}]},
        "content not a string": {**SAMPLE_PAYLOAD, "blocks": [{**SAMPLE_TASK, "content": {}}]},
    }

    def test_payload_that_crashes_the_app_is_a_fast_render_error(self):
        for name, payload in self.PAYLOADS.items():
            with self.subTest(name):
                started = time.monotonic()
                with self.assertRaisesRegex(RenderError, "could not render the payload"):
                    render("receipt", payload=payload)
                self.assertLess(time.monotonic() - started, FAST_REJECT_SECONDS)


class RenderErrorTest(unittest.TestCase):
    def assertRenderError(self, kind: str, **content) -> None:
        with self.assertRaises(RenderError) as caught:
            render(kind, **content)
        self.assertTrue(str(caught.exception))

    def test_unknown_kind_is_a_render_error(self):
        self.assertRenderError("poster", payload=SAMPLE_PAYLOAD)

    def test_receipt_without_payload_is_a_render_error(self):
        self.assertRenderError("receipt")

    def test_receipt_payload_that_is_not_an_object_is_a_render_error(self):
        self.assertRenderError("receipt", payload=["not", "an", "object"])

    def test_receipt_payload_nested_900_deep_is_not_a_server_fault(self):
        # The receipt payload reaches the page as a file, so deep nesting never meets Playwright's serializer.
        rendered = render("receipt", payload={**SAMPLE_PAYLOAD, "deep": _nested(900)})
        self.assertEqual(rendered.width, PRINT_WIDTH_DOTS)

    def test_receipt_payload_the_app_rejects_is_a_render_error_with_the_app_message(self):
        with self.assertRaisesRegex(RenderError, "schemaVersion 999 \\(expected 2\\)"):
            render("receipt", payload={**SAMPLE_PAYLOAD, "schemaVersion": 999})

    def test_image_without_bytes_is_a_render_error(self):
        self.assertRenderError("image")

    def test_empty_image_is_a_render_error(self):
        self.assertRenderError("image", image=b"")

    def test_non_image_upload_is_a_plain_render_error_not_a_pil_error(self):
        with self.assertRaises(RenderError) as caught:
            render("image", image=b"%PDF-1.7\n" + b"x" * 2000)
        self.assertEqual(
            str(caught.exception), "the upload is not an image this server can read; send a JPEG or PNG"
        )

    def test_truncated_image_is_a_render_error(self):
        whole = _photo((640, 480), "RGB", "PNG")
        self.assertRenderError("image", image=whole[: len(whole) // 2])

    def test_missing_web_build_is_a_server_fault_that_says_how_to_fix_it(self):
        with tempfile.TemporaryDirectory() as empty, mock.patch.object(render_job, "DIST_DIR", Path(empty)):
            with self.assertRaises(RuntimeError) as caught:
                render("receipt", payload=SAMPLE_PAYLOAD)
        self.assertNotIsInstance(caught.exception, RenderError)
        self.assertIn("make web-build", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
