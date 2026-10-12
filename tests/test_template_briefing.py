import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ticket_templates import TemplateError, open_render_page, render_template  # noqa: E402

SAMPLE = json.loads((ROOT / "samples" / "templates" / "briefing.json").read_text(encoding="utf-8"))
HAS_WEB = (ROOT / "web" / "node_modules").is_dir()

# Every element under #receipt: off whole pixels, wider than the paper, or clipping its content.
_GEOMETRY_JS = """
() => {
  const receipt = document.querySelector('#receipt'), origin = receipt.getBoundingClientRect();
  const fractional = [], outside = [], clipped = [];
  // A value that wraps prints as two wrong values: tile figures and the hero stay on one line.
  const wrapped = [...receipt.querySelectorAll('.rp-tile-v, .display-hero')]
    .filter((element) => element.getBoundingClientRect().height >= 2 * parseInt(getComputedStyle(element).lineHeight))
    .map((element) => element.textContent);
  for (const element of receipt.querySelectorAll('*')) {
    const r = element.getBoundingClientRect(), name = `${element.tagName}.${element.className} "${element.textContent.slice(0, 20)}"`;
    if ([r.left - origin.left, r.top - origin.top, r.width, r.height].some((v) => v % 1)) fractional.push(name);
    if (r.left < origin.left || r.right > origin.left + 384) outside.push(name);
    if (element.scrollWidth > element.clientWidth) clipped.push(name);
  }
  return { fractional, outside, clipped, wrapped };
}
"""


def briefing(**data):
    payload = copy.deepcopy(SAMPLE)
    payload["data"].update(data)
    return payload


def widest(**weather):
    return briefing(
        weekday="W" * 12,
        dateLine="W" * 40,
        weather={"temp": -99, "condition": "W" * 24, "high": 199, "low": -99, "note": "W" * 40, "advice": "W" * 40, **weather},
        counts={"meetings": 999, "tasks": 999, "deadlines": 999},
        firstUp=[{"time": "WWWWW", "title": "W" * 60}] * 3,
        oneThing="W" * 140,
    )


def setUpModule():
    if HAS_WEB:
        subprocess.run(["npm", "run", "build"], cwd=ROOT / "web", check=True, capture_output=True)


@unittest.skipUnless(HAS_WEB, "needs web dependencies: make setup-web")
class BriefingTest(unittest.TestCase):
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

    def assert_fits(self, payload):
        image = render_template(self.page, payload)
        self.assertEqual(image.width, 384)
        self.assertEqual(self.page.evaluate(_GEOMETRY_JS), {"fractional": [], "outside": [], "clipped": [], "wrapped": []})

    def text(self):
        return self.page.evaluate("document.querySelector('#receipt').innerText")

    def test_sample_and_extremes_fit_on_whole_pixels(self):
        for name, payload in (
            ("sample", SAMPLE),
            ("widest", widest()),
            ("cold", widest(temp=-40, high=-40, low=-40)),
            ("hot", widest(temp=100, high=100, low=100)),
            ("short time", briefing(firstUp=[{"time": "9:00", "title": "Standup"}])),
        ):
            with self.subTest(name):
                self.assert_fits(payload)

    def test_temperatures_print_with_a_degree_and_a_minus(self):
        render_template(self.page, briefing(weather={"temp": -4, "condition": "Snow", "high": 0, "low": -12}))
        self.assertIn("−4°", self.text())
        self.assertIn("H 0° · L −12°", self.text())

    def test_optional_blocks_leave_no_trace(self):
        self.assert_fits(briefing(weather=None, firstUp=[], oneThing=None))
        text = self.text()
        self.assertIn("THURSDAY", text)
        self.assertIn("DEADLINES", text)
        for absent in ("°", "FIRST UP", "THE ONE THING"):
            self.assertNotIn(absent, text)

    def test_out_of_range_values_are_refused(self):
        for data, pattern in (
            ({"weekday": "W" * 13}, r"^data\.weekday: expected at most 12 characters$"),
            ({"counts": {"meetings": 1000, "tasks": 0, "deadlines": 0}},
             r"^data\.counts\.meetings: expected an integer from 0 to 999$"),
            ({"counts": {"meetings": 1, "tasks": -1, "deadlines": 0}},
             r"^data\.counts\.tasks: expected an integer from 0 to 999$"),
            ({"weather": {**SAMPLE["data"]["weather"], "temp": 14.5}},
             r"^data\.weather\.temp: expected an integer from -99 to 199$"),
            ({"weather": {**SAMPLE["data"]["weather"], "low": -100}},
             r"^data\.weather\.low: expected an integer from -99 to 199$"),
            ({"firstUp": SAMPLE["data"]["firstUp"] * 2}, r"^data\.firstUp: expected at most 3 items$"),
            ({"weekday": ""}, r"^data\.weekday: expected non-blank text$"),
            ({"dateLine": " "}, r"^data\.dateLine: expected non-blank text$"),
            ({"weather": {**SAMPLE["data"]["weather"], "condition": "\t"}},
             r"^data\.weather\.condition: expected non-blank text$"),
            ({"firstUp": [{"time": "", "title": "Standup"}]}, r"^data\.firstUp\[0\]\.time: expected non-blank text$"),
            ({"firstUp": [{"time": "09:00", "title": "  "}]}, r"^data\.firstUp\[0\]\.title: expected non-blank text$"),
            # Optional text may be absent, never blank: a blank would print an empty Callout or a bare arrow.
            ({"oneThing": "   "}, r"^data\.oneThing: expected non-blank text$"),
            ({"weather": {**SAMPLE["data"]["weather"], "advice": " "}},
             r"^data\.weather\.advice: expected non-blank text$"),
            ({"weather": {**SAMPLE["data"]["weather"], "note": ""}}, r"^data\.weather\.note: expected non-blank text$"),
        ):
            with self.subTest(pattern), self.assertRaisesRegex(TemplateError, pattern):
                render_template(self.page, briefing(**data))


if __name__ == "__main__":
    unittest.main()
