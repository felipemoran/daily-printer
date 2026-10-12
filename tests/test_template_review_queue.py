import copy
import json
import sys
import unittest
from pathlib import Path

from tests.web_build import build_web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ticket_templates import TemplateError, open_render_page, render_template  # noqa: E402

SAMPLE = json.loads((ROOT / "samples" / "templates" / "review-queue.json").read_text(encoding="utf-8"))
# Spans are text runs and T.Tag, whose width follows the glyph advance and is fractional.
FRACTIONAL_BOXES_JS = """() => [...document.querySelectorAll('#receipt :not(span, br)')].flatMap((element) => {
  const r = element.getBoundingClientRect();
  return [r.x, r.y, r.width, r.height].every(Number.isInteger) ? [] : [element.outerHTML.slice(0, 80)];
})"""
# A design-system cell clips with overflow:hidden; a clipped value prints wrong while the render succeeds.
OVERFLOWING_JS = """() => {
  const right = document.querySelector('#receipt').getBoundingClientRect().right;
  return [...document.querySelectorAll('#receipt, #receipt *')].flatMap((element) =>
    element.scrollWidth > element.clientWidth || element.getBoundingClientRect().right > right
      ? [element.outerHTML.slice(0, 80)] : []);
}"""


def setUpModule():
    build_web()


def pr(number=1, age_days=0, **fields):
    return {"number": number, "title": "Fix it", "area": "api", "added": 3, "removed": 1, "ageDays": age_days, **fields}


def queue(prs):
    payload = copy.deepcopy(SAMPLE)
    payload["data"]["prs"] = prs
    return payload


class ReviewQueueTest(unittest.TestCase):
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

    def render_lines(self, payload):
        image = render_template(self.page, payload)
        self.assertIsNotNone(image.convert("L").point(lambda value: 255 - value).getbbox(), "blank render")
        return self.page.evaluate("document.querySelector('#receipt').innerText").split("\n")

    def test_sample_lists_every_pr_on_whole_pixels(self):
        lines = self.render_lines(SAMPLE)
        self.assertIn("6 WAITING ON YOU · OLDEST 4D", lines)
        self.assertIn("api · +312 −48", lines)
        self.assertEqual(lines.count("#492"), 1)
        self.assertEqual(self.page.evaluate(FRACTIONAL_BOXES_JS), [])

    def test_stale_starts_after_two_days(self):
        lines = self.render_lines(queue([pr(1, 2), pr(2, 3)]))
        self.assertIn("2D", lines)
        self.assertIn("STALE 3D", lines)
        self.assertNotIn("STALE 2D", lines)
        self.assertIn("2 WAITING ON YOU · OLDEST 3D", lines)

    def test_oldest_is_the_largest_age_in_any_order(self):
        self.assertIn("3 WAITING ON YOU · OLDEST 9D", self.render_lines(queue([pr(1, 1), pr(2, 9), pr(3, 0)])))

    def test_rows_print_oldest_first_and_stable_for_ties(self):
        lines = self.render_lines(queue([pr(1, 0), pr(2, 5), pr(3, 0), pr(4, 2)]))
        numbers = [line for line in lines if line.startswith("#")]
        self.assertEqual(numbers, ["#2", "#4", "#1", "#3"])

    def test_widest_values_fit_unclipped(self):
        widest = pr(999_999_999_999, 9999, title="x" * 64, area="a" * 10, added=999_999, removed=999_999)
        lines = self.render_lines(queue([widest, pr(2, 1000, added=123_456, removed=654_321)] + [pr(3)] * 18))
        self.assertIn("#999999999999", lines)
        self.assertIn("STALE 1000D", lines)
        self.assertIn("aaaaaaaaaa · +999999 −999999", lines)
        self.assertIn("20 WAITING ON YOU · OLDEST 9999D", lines)
        self.assertEqual(self.page.evaluate(OVERFLOWING_JS), [])

    def test_tallest_queue_fits_the_render_cap(self):
        # Words that cannot share a line: 64 characters wrap to 3 lines.
        title = " ".join(("a" * 20, "b" * 20, "c" * 22))
        tallest = pr(999_999_999_999, 9999, title=title, area="a" * 10, added=999_999, removed=999_999)
        image = render_template(self.page, queue([tallest] * 20))
        heights = self.page.evaluate("""() => ['.body-strong', '.meta'].map((selector) =>
          [...document.querySelectorAll(`#receipt ${selector}`)].map((element) => element.offsetHeight))""")
        self.assertEqual(set(heights[0][1:]), {72}, "titles: 3 lines")
        self.assertEqual(set(heights[1]), {24}, "meta: 1 line")
        self.assertLess(image.height, 4000)

    def test_empty_queue_says_so(self):
        lines = self.render_lines(queue([]))
        self.assertIn("0 WAITING ON YOU", lines)
        self.assertIn("NOTHING TO REVIEW", lines)
        self.assertFalse(any("OLDEST" in line for line in lines))

    def test_invalid_data_names_the_field_path(self):
        for prs, pattern in (
            ([pr(age_days=1.5)], r"^data\.prs\[0\]\.ageDays: expected a whole number from 0 to 9999$"),
            ([pr(age_days=10_000)], r"^data\.prs\[0\]\.ageDays: expected a whole number from 0 to 9999$"),
            ([pr(added=-1)], r"^data\.prs\[0\]\.added: expected a whole number from 0 to 999999$"),
            ([pr(added=1e21)], r"^data\.prs\[0\]\.added: expected a whole number from 0 to 999999$"),
            ([pr(removed=1_000_000)], r"^data\.prs\[0\]\.removed: expected a whole number from 0 to 999999$"),
            ([pr(title="x" * 65)], r"^data\.prs\[0\]\.title: expected at most 64 characters$"),
            ([pr(area="x" * 11)], r"^data\.prs\[0\]\.area: expected at most 10 characters$"),
            ([pr(number=10**12)], r"^data\.prs\[0\]\.number: expected a whole number from 0 to 999999999999$"),
            ([pr(removed="4")], r"^data\.prs\[0\]\.removed: expected a whole number from 0 to 999999$"),
            ([pr(number=None)], r"^data\.prs\[0\]\.number: expected a whole number from 0 to 999999999999$"),
            ([pr()] * 21, r"^data\.prs: expected at most 20 items$"),
        ):
            with self.subTest(pattern), self.assertRaisesRegex(TemplateError, pattern):
                render_template(self.page, queue(prs))

    def test_blank_text_is_refused(self):
        for blank in ("", " \t"):
            for field in ("title", "area"):
                with self.subTest(field=field, blank=blank), \
                        self.assertRaisesRegex(TemplateError, rf"^data\.prs\[0\]\.{field}: expected non-blank text$"):
                    render_template(self.page, queue([pr(**{field: blank})]))


if __name__ == "__main__":
    unittest.main()
