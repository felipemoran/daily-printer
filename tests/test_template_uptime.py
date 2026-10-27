import copy
import json
import sys
import unittest
from pathlib import Path

from tests.web_build import build_web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ticket_templates import TemplateError, launch_browser, open_render_page, render_template  # noqa: E402

SAMPLE = json.loads((ROOT / "samples" / "templates" / "uptime.json").read_text(encoding="utf-8"))
OK_DAY = "o" * 24

# Widest accepted content: every string at its limit, in the widest glyphs.
EDGE = {
    "template": "uptime",
    "schemaVersion": 1,
    "data": {
        "service": "W" * 60,
        "uptimePct": 100,
        "days": [{"label": "WWWWW", "hours": "xdo" * 8}] * 7,
        "incidents": [{"when": "W" * 9, "text": "W" * 80}] * 6,
    },
}

OVERFLOW = """() => {
  const receipt = document.querySelector('#receipt'), left = receipt.getBoundingClientRect().left;
  return [...receipt.querySelectorAll('*')]
    .filter((el) => el.scrollWidth > el.clientWidth || el.getBoundingClientRect().right - left > 384)
    .map((el) => el.outerHTML.slice(0, 80));
}"""

GEOMETRY = """() => {
  const receipt = document.querySelector('#receipt'), origin = receipt.getBoundingClientRect();
  const box = (el) => { const r = el.getBoundingClientRect(); return [r.left - origin.left, r.top - origin.top, r.width, r.height]; };
  return {
    cells: [...receipt.querySelectorAll('.rp-cell')].map(box),
    ticks: [...receipt.querySelectorAll('.micro span')].map((el) => [el.textContent, box(el)[0]]),
  };
}"""


def uptime(**data):
    payload = copy.deepcopy(SAMPLE)
    payload["data"].update(data)
    return payload


def setUpModule():
    build_web()


class UptimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright

        cls.playwright = sync_playwright().start()
        cls.browser = launch_browser(cls.playwright)
        cls.page = open_render_page(cls.browser)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def test_refuses_bad_data(self):
        cases = (
            (uptime(days=[{"label": "MON", "hours": "o" * 23}]), r"^data\.days\[0\]\.hours: expected 24 characters"),
            (uptime(days=[{"label": "MON", "hours": "o" * 25}]), r"^data\.days\[0\]\.hours: expected 24 characters"),
            (uptime(days=[{"label": "MON", "hours": "o" * 23 + "0"}]), r"^data\.days\[0\]\.hours: expected 24 characters"),
            (uptime(days=[{"label": "MON", "hours": ["o"] * 24}]), r"^data\.days\[0\]\.hours: expected 24 characters"),
            (uptime(days=[{"label": "MONDAY", "hours": OK_DAY}]), r"^data\.days\[0\]\.label: expected 1 to 5"),
            (uptime(days=[{"label": "月曜日", "hours": OK_DAY}]), r"^data\.days\[0\]\.label: expected 1 to 5"),
            (uptime(days=[]), r"^data\.days: expected at least 1 item$"),
            (uptime(days=[{"label": "MON", "hours": OK_DAY}] * 8), r"^data\.days: expected at most 7 items$"),
            (uptime(incidents=[{"when": "MON", "text": "x"}] * 7), r"^data\.incidents: expected at most 6 items$"),
            (uptime(incidents=[{"when": "MON 14:00h", "text": "x"}]), r"^data\.incidents\[0\]\.when: expected at most 9"),
            (uptime(uptimePct=100.5), r"^data\.uptimePct: expected a number from 0 to 100$"),
            (uptime(uptimePct="99.42%"), r"^data\.uptimePct: expected number$"),
            (uptime(service="W" * 61), r"^data\.service: expected at most 60 characters$"),
            (uptime(service=""), r"^data\.service: expected non-blank text$"),
            (uptime(days=[{"label": "   ", "hours": OK_DAY}]), r"^data\.days\[0\]\.label: expected non-blank text$"),
            (uptime(incidents=[{"when": "", "text": "x"}]), r"^data\.incidents\[0\]\.when: expected non-blank text$"),
            (uptime(incidents=[{"when": "MON", "text": " "}]), r"^data\.incidents\[0\]\.text: expected non-blank text$"),
        )
        for payload, pattern in cases:
            with self.subTest(pattern), self.assertRaisesRegex(TemplateError, pattern):
                render_template(self.page, payload)

    def test_grid_fills_the_paper_on_whole_pixels(self):
        render_template(self.page, SAMPLE)
        geometry = self.page.evaluate(GEOMETRY)
        cells = geometry["cells"]
        self.assertEqual(len(cells), 7 * 24)
        for cell in cells:
            self.assertEqual(cell, [round(value) for value in cell])
            self.assertEqual(cell[2:], [11, 22])
        first_row = sorted(cell[0] for cell in cells[:24])
        self.assertEqual(first_row, [51 + hour * 14 for hour in range(24)])
        self.assertEqual(first_row[-1] + 11, 384)
        self.assertEqual(geometry["ticks"], [[f"{hour:02d}", first_row[hour]] for hour in (0, 6, 12, 18)])

    def test_widest_content_stays_inside_its_boxes(self):
        image = render_template(self.page, EDGE)
        self.assertEqual(image.width, 384)
        self.assertEqual(self.page.evaluate(OVERFLOW), [])
        self.assertIn("100.00%", self.page.inner_text("#receipt"))

    def test_uptime_is_truncated_not_rounded(self):
        for pct, text in ((99.999, "99.99%"), (100, "100.00%"), (1.13, "1.13%"), (0, "0.00%")):
            with self.subTest(pct):
                render_template(self.page, uptime(uptimePct=pct))
                self.assertEqual(self.page.inner_text("#receipt .display-xl"), text)

    def test_no_incidents_prints_a_zero_count(self):
        render_template(self.page, uptime(incidents=None))
        self.assertIn("INCIDENTS (0)", self.page.inner_text("#receipt"))
        self.assertEqual(self.page.locator("#receipt .rp-log").count(), 0)


if __name__ == "__main__":
    unittest.main()
