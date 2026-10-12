import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ticket_templates import TemplateError, open_render_page, render_template  # noqa: E402

FOCUS = json.loads((ROOT / "samples" / "templates" / "focus.json").read_text(encoding="utf-8"))
HAS_WEB = (ROOT / "web" / "node_modules").is_dir()

# The title is the first display element; the stub date comes after it.
_TITLE_JS = """
() => {
  const title = document.querySelector('#receipt [class^="display-"]');
  return { size: title.className, width: title.scrollWidth, lines: Math.round(title.offsetHeight / parseFloat(getComputedStyle(title).lineHeight)) };
}
"""

# Clipped or overflowing text prints a wrong value while the render still succeeds.
_OVERFLOW_JS = """
() => [...document.querySelectorAll('#receipt, #receipt *')]
  .filter((el) => el.scrollWidth > el.clientWidth && el.clientWidth > 0 || el.getBoundingClientRect().right > 384)
  .map((el) => el.outerHTML.slice(0, 80))
"""


def setUpModule():
    if HAS_WEB:
        subprocess.run(["npm", "run", "build"], cwd=ROOT / "web", check=True, capture_output=True)


def focus(**data):
    payload = copy.deepcopy(FOCUS)
    payload["data"].update(data)
    for key in [key for key, value in data.items() if value is None]:
        del payload["data"][key]
    return payload


@unittest.skipUnless(HAS_WEB, "needs web dependencies: make setup-web")
class FocusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright

        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)
        cls.page = open_render_page(cls.browser)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def render(self, payload, page=None):
        page = page or self.page
        image = render_template(page, payload)
        self.assertIsNotNone(image.convert("L").point(lambda value: 255 - value).getbbox(), "blank render")
        return page.evaluate(_TITLE_JS)

    def test_title_takes_the_largest_size_its_longest_word_fits(self):
        # A fresh page: the first render must wait for Archivo before it measures.
        page = open_render_page(self.browser)
        for title, size in (
            ("Fix performance regression", "display-md"),  # PERFORMANCE: 446 at lg, 356 at md
            ("Ship billing migration", "display-lg"),  # MIGRATION: 340 dots at display-lg
            ("Infrastructure audit", "display-sm"),  # INFRASTRUCTURE: 417 at md, 278 at sm
        ):
            with self.subTest(title):
                result = self.render(focus(title=title), page)
                self.assertEqual(result["size"], size)
                self.assertLessEqual(result["width"], 384)
                self.assertEqual(page.evaluate(_OVERFLOW_JS), [])

    def test_long_title_wraps_at_words_and_keeps_its_size(self):
        result = self.render(focus(title="Ship the billing migration to all of the regions we run"))
        self.assertEqual(result["size"], "display-lg")
        self.assertGreater(result["lines"], 2)

    def test_edge_payload_never_overflows_the_paper(self):
        payload = focus(
            id="W" * 12,
            title="W" * 40 + " " + "W" * 19,
            startedAt="W" * 10,
            estimate="W" * 10,
            pomodoros=12,
            noteLines=8,
            date="W" * 6,
        )
        self.assertEqual(len(payload["data"]["title"]), 60)
        self.assertEqual(self.render(payload)["size"], "display-sm")
        self.assertEqual(self.page.evaluate(_OVERFLOW_JS), [])

    def test_bitmap_is_the_laid_out_receipt_on_fresh_pages(self):
        # A fresh page draws characters the bundled fonts lack from a system face that can change at capture.
        for data in (
            {"id": "ШШШШШШШШШШШ", "title": "Миграция биллинга"},
            {"title": "账单迁移 billing migration"},
            {"id": "ÉTÉ-118", "title": "Déjà vu façade — “naïve” Œuvre", "estimate": "2h · €"},
        ):
            for attempt in range(3):
                with self.subTest(data=data, attempt=attempt):
                    page = open_render_page(self.browser)
                    try:
                        image = render_template(page, focus(**data))
                        self.assertEqual(image.height, page.evaluate("() => document.querySelector('#receipt').offsetHeight"))
                        bottom = image.crop((0, image.height - 8, image.width, image.height))
                        self.assertIsNone(bottom.convert("L").point(lambda value: 255 - value).getbbox(), "ink in the feed")
                    finally:
                        page.close()

    def test_counts_default_and_draw_whole_pixel_boxes(self):
        for pomodoros, notes, expected in ((None, None, (6, 4)), (1, 1, (1, 1)), (12, 8, (12, 8))):
            with self.subTest(pomodoros=pomodoros, notes=notes):
                self.render(focus(pomodoros=pomodoros, noteLines=notes))
                boxes = self.page.evaluate("() => [...document.querySelectorAll('#receipt .rp-boxes > div')].map((b) => b.getBoundingClientRect())")
                lines = self.page.evaluate("() => document.querySelectorAll('#receipt .rp-lines > div').length")
                self.assertEqual((len(boxes), lines), expected)
                for box in boxes:
                    self.assertTrue(all(float(box[key]).is_integer() for key in ("x", "y", "width", "height")), box)
                    self.assertEqual(box["width"], box["height"])

    def test_hollow_boxes_stay_hollow(self):
        self.render(FOCUS)
        self.assertEqual(self.page.evaluate("() => document.querySelectorAll('#receipt .rp-fill-solid').length"), 0)

    def test_optional_fields_can_be_left_out(self):
        self.render(focus(id=None, startedAt=None, estimate=None))
        text = self.page.evaluate("() => document.querySelector('#receipt').innerText")
        self.assertNotIn("BIL-118", text)
        self.assertNotIn("started", text)
        self.assertIn("NOW WORKING ON", text)

    def test_bad_data_is_refused(self):
        for data, pattern in (
            ({"pomodoros": 13}, r"data\.pomodoros: expected an integer from 1 to 12"),
            ({"pomodoros": 0}, r"data\.pomodoros: expected an integer from 1 to 12"),
            ({"pomodoros": 2.5}, r"data\.pomodoros: expected an integer from 1 to 12"),
            ({"noteLines": 9}, r"data\.noteLines: expected an integer from 1 to 8"),
            ({"id": "W" * 13}, r"data\.id: expected at most 12 characters"),
            ({"title": "W" * 61}, r"data\.title: expected at most 60 characters"),
            ({"title": "  "}, r"data\.title: expected non-empty text"),
            ({"date": "01.10.26"}, r"data\.date: expected at most 6 characters"),
            ({"startedAt": "W" * 11}, r"data\.startedAt: expected at most 10 characters"),
            ({"done": True}, r"data\.done: unknown field"),
        ):
            with self.subTest(data), self.assertRaisesRegex(TemplateError, pattern):
                render_template(self.page, focus(**data))


if __name__ == "__main__":
    unittest.main()
