import copy
import json
import sys
import unittest
from pathlib import Path

from tests.web_build import build_web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ticket_templates import TemplateError, open_render_page, render_template  # noqa: E402

REPORT = json.loads((ROOT / "samples" / "templates" / "report.json").read_text(encoding="utf-8"))
# BarList track: 384 paper - 76 label - 52 value - 24 gaps. Columns bar area: 180.
TRACK, COLUMN = 232, 180
# .rp-bar-b is border-box with a 2px border: a zero previous-week bar stays 4px wide.
EMPTY_PREV = 4

_GEOMETRY_JS = """
() => {
  const widths = (selector) => [...document.querySelectorAll(selector)].map((bar) => bar.getBoundingClientRect().width);
  return {
    a: widths('#receipt .rp-bar-a'),
    b: widths('#receipt .rp-bar-b'),
    columns: [...document.querySelectorAll('#receipt .rp-col-bar')].map((bar) => bar.getBoundingClientRect().height),
    bars: [...document.querySelectorAll('#receipt .rp-barrow-v')].map((label) => label.textContent),
    values: [...document.querySelectorAll('#receipt .rp-col > span')].map((label) => label.textContent),
    kpiColumns: [...document.querySelectorAll('#receipt .rp-tiles')].map((grid) => getComputedStyle(grid).gridTemplateColumns.split(' ').length)[0],
  };
}
"""

# Text that is clipped by its cell, spills out of its parent, or runs off the paper.
_OVERFLOW_JS = """
() => {
  const paper = document.querySelector('#receipt').getBoundingClientRect();
  const selector = '.rp-barrow-l, .rp-barrow-v, .rp-col > span, .rp-cols-x span, .rp-tile-v';
  return [...document.querySelectorAll(selector)].filter((cell) => {
    const box = cell.getBoundingClientRect(), parent = cell.parentElement.getBoundingClientRect();
    return cell.scrollWidth > cell.clientWidth || box.left < parent.left || box.right > parent.right
      || box.left < paper.left || box.right > paper.left + 384;
  }).map((cell) => `${cell.className || cell.parentElement.className}: ${cell.textContent}`);
}
"""
BIG = [9999, 12345, 123456, 1234567, 999.5, 0.25, 1e12]


def setUpModule():
    build_web()


def report(**data):
    payload = copy.deepcopy(REPORT)
    payload["data"].update(data)
    return payload


class ReportTest(unittest.TestCase):
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

    def geometry(self, payload):
        image = render_template(self.page, payload)
        self.assertIsNotNone(image.convert("L").point(lambda value: 255 - value).getbbox(), "blank render")
        return self.page.evaluate(_GEOMETRY_JS)

    def test_largest_value_of_either_week_spans_the_track(self):
        geometry = self.geometry(report(channels=[
            {"label": "A", "value": 50, "prev": 200},
            {"label": "B", "value": 100, "prev": 0},
        ]))
        self.assertEqual(geometry["a"], [58, 116])
        self.assertEqual(geometry["b"], [TRACK, EMPTY_PREV])

    def test_tallest_day_fills_the_columns_even_below_one(self):
        geometry = self.geometry(report(days=[{"label": "M", "value": 0.5}, {"label": "T", "value": 0.25}]))
        self.assertEqual(geometry["columns"], [COLUMN, COLUMN / 2])
        self.assertEqual(geometry["values"], ["0.5", "0.25"])

    def test_all_zero_values_render_empty_bars(self):
        geometry = self.geometry(report(
            channels=[{"label": "A", "value": 0, "prev": 0}] * 3,
            days=[{"label": "M", "value": 0}] * 7,
        ))
        self.assertEqual(geometry["a"] + geometry["columns"], [0] * 10)
        self.assertEqual(geometry["b"], [EMPTY_PREV] * 3)
        self.assertEqual(geometry["values"], ["0"] * 7)

    def test_geometry_is_whole_pixels(self):
        geometry = self.geometry(REPORT)
        for size in geometry["a"] + geometry["b"] + geometry["columns"]:
            self.assertEqual(size, int(size))

    def test_empty_lists_still_render_the_masthead(self):
        self.geometry(report(kpis=[], channels=[], days=[]))

    def test_large_numbers_fit_their_cells(self):
        image = render_template(self.page, report(
            kpis=[{"label": "TICKETS IN", "value": "12,345"}] * 3,
            channels=[{"label": "WWWWWWW", "value": value, "prev": 0} for value in BIG],
            days=[{"label": "WWWW", "value": value} for value in BIG],
        ))
        self.assertEqual(image.width, 384)
        self.assertEqual(self.page.evaluate(_OVERFLOW_JS), [])
        geometry = self.page.evaluate(_GEOMETRY_JS)
        self.assertEqual(geometry["bars"], ["9,999", "12.3K", "123K", "1.23M", "999.5", "0.25", "1T"])
        self.assertEqual(geometry["values"], ["10K", "12K", "123K", "1.2M", "1K", "0.25", "1T"])

    def test_negative_zero_prints_as_zero(self):
        geometry = self.geometry(report(
            channels=[{"label": "A", "value": -0.0, "prev": -0.0}],
            days=[{"label": "M", "value": -0.0}],
        ))
        self.assertEqual((geometry["bars"], geometry["values"]), (["0"], ["0"]))

    def test_kpi_grid_has_no_empty_tile(self):
        for count, columns in ((1, 1), (2, 2), (3, 1), (4, 2)):
            with self.subTest(count):
                geometry = self.geometry(report(kpis=REPORT["data"]["kpis"][:count]))
                self.assertEqual(geometry["kpiColumns"], columns)

    def test_invalid_data(self):
        for data, pattern in (
            ({"channels": [{"label": "A", "value": -1, "prev": 0}]}, r"^data\.channels\[0\]\.value: expected a number from 0 to 1e12$"),
            ({"days": [{"label": "M", "value": 1e12 + 1}]}, r"^data\.days\[0\]\.value: expected a number from 0 to 1e12$"),
            ({"channels": [{"label": "SOCIAL M", "value": 1, "prev": 1}]}, r"^data\.channels\[0\]\.label: expected at most 7 characters$"),
            ({"days": [{"label": "WEDNE", "value": 1}]}, r"^data\.days\[0\]\.label: expected at most 4 characters$"),
            ({"days": [{"label": "M", "value": "3"}]}, r"^data\.days\[0\]\.value: expected number$"),
            ({"days": [{"label": "M", "value": 1}] * 8}, r"^data\.days: expected at most 7 items$"),
            ({"channels": [{"label": "A", "value": 1, "prev": 1}] * 9}, r"^data\.channels: expected at most 8 items$"),
            ({"kpis": [{"label": "A", "value": "1"}] * 5}, r"^data\.kpis: expected at most 4 items$"),
            ({"kpis": [{"label": "A", "value": "1234567"}]}, r"^data\.kpis\[0\]\.value: expected at most 6 characters$"),
            ({"week": 54}, r"^data\.week: expected a whole number from 1 to 53$"),
        ):
            with self.subTest(pattern), self.assertRaisesRegex(TemplateError, pattern):
                render_template(self.page, report(**data))

    def test_blank_text_is_refused(self):
        kpi = {"label": "A", "value": "1", "note": "n"}
        for blank in ("", " \t"):
            for data, field in (
                ({"range": blank}, "range"),
                ({"title": blank}, "title"),
                ({"kpis": [{**kpi, "label": blank}]}, r"kpis\[0\]\.label"),
                ({"kpis": [{**kpi, "value": blank}]}, r"kpis\[0\]\.value"),
                ({"kpis": [{**kpi, "note": blank}]}, r"kpis\[0\]\.note"),
                ({"channels": [{"label": blank, "value": 1, "prev": 1}]}, r"channels\[0\]\.label"),
                ({"days": [{"label": blank, "value": 1}]}, r"days\[0\]\.label"),
            ):
                with self.subTest(field=field, blank=blank), \
                        self.assertRaisesRegex(TemplateError, rf"^data\.{field}: expected non-blank text$"):
                    render_template(self.page, report(**data))


if __name__ == "__main__":
    unittest.main()
