import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ticket_templates import TemplateError, open_render_page, render_template  # noqa: E402

REPORT = json.loads((ROOT / "samples" / "templates" / "report.json").read_text(encoding="utf-8"))
HAS_WEB = (ROOT / "web" / "node_modules").is_dir()
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
    values: [...document.querySelectorAll('#receipt .rp-col > span')].map((label) => label.textContent),
  };
}
"""


def setUpModule():
    if HAS_WEB:
        subprocess.run(["npm", "run", "build"], cwd=ROOT / "web", check=True, capture_output=True)


def report(**data):
    payload = copy.deepcopy(REPORT)
    payload["data"].update(data)
    return payload


@unittest.skipUnless(HAS_WEB, "needs web dependencies: make setup-web")
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

    def test_invalid_data(self):
        for data, pattern in (
            ({"channels": [{"label": "A", "value": -1, "prev": 0}]}, r"^data\.channels\[0\]\.value: expected a non-negative number$"),
            ({"days": [{"label": "M", "value": "3"}]}, r"^data\.days\[0\]\.value: expected number$"),
            ({"days": [{"label": "M", "value": 1}] * 8}, r"^data\.days: expected at most 7 items$"),
            ({"channels": [{"label": "A", "value": 1, "prev": 1}] * 9}, r"^data\.channels: expected at most 8 items$"),
            ({"kpis": [{"label": "A", "value": "1"}] * 5}, r"^data\.kpis: expected at most 4 items$"),
            ({"kpis": [{"label": "A", "value": "1234567"}]}, r"^data\.kpis\[0\]\.value: expected at most 6 characters$"),
            ({"week": 54}, r"^data\.week: expected an integer from 1 to 53$"),
        ):
            with self.subTest(pattern), self.assertRaisesRegex(TemplateError, pattern):
                render_template(self.page, report(**data))


if __name__ == "__main__":
    unittest.main()
