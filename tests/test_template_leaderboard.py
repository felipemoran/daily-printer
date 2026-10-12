import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ticket_templates import TemplateError, open_render_page, render_template  # noqa: E402

SAMPLE = json.loads((ROOT / "samples" / "templates" / "leaderboard.json").read_text(encoding="utf-8"))
HAS_WEB = (ROOT / "web" / "node_modules").is_dir()
PERSON = {"name": "P. Ruiz", "amount": "$298K", "pct": 99}


def leaderboard(**data):
    payload = copy.deepcopy(SAMPLE)
    payload["data"].update(data)
    return payload


# Every list and string at its limit.
def widest(name):
    return leaderboard(
        title="W" * 24,
        status="W" * 12,
        people=[{"name": name, "amount": "WWWWW", "pct": 1000}] * 10,
        total={"amount": "W" * 8, "pct": 1000},
    )


OVERFLOW = """() => {
  const receipt = document.querySelector('#receipt'), left = receipt.getBoundingClientRect().left;
  return [...receipt.querySelectorAll('*')]
    .filter((el) => el.scrollWidth > el.clientWidth || el.getBoundingClientRect().right - left > 384)
    .map((el) => el.outerHTML.slice(0, 80));
}"""

GEOMETRY = """() => {
  const receipt = document.querySelector('#receipt'), left = receipt.getBoundingClientRect().left;
  const box = (el) => { const r = el.getBoundingClientRect(); return [r.left - left, r.width]; };
  const quota = [...receipt.querySelectorAll('.micro span')].find((el) => el.textContent === 'QUOTA');
  return {
    tracks: [...receipt.querySelectorAll('.rp-barpair')].map(box),
    bars: [...receipt.querySelectorAll('.rp-bar-a')].map((el) => [...box(el), !el.className.includes('rp-fill-')]),
    marks: [...receipt.querySelectorAll('.rp-mark')].map(box),
    quota: quota && box(quota),
  };
}"""


def setUpModule():
    if HAS_WEB:
        subprocess.run(["npm", "run", "build"], cwd=ROOT / "web", check=True, capture_output=True)


@unittest.skipUnless(HAS_WEB, "needs web dependencies: make setup-web")
class LeaderboardTest(unittest.TestCase):
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
        render_template(self.page, payload)
        return self.page.evaluate(GEOMETRY)

    def test_refuses_bad_data(self):
        cases = (
            (leaderboard(title=""), r"^data\.title: expected non-blank text$"),
            (leaderboard(status="  "), r"^data\.status: expected non-blank text$"),
            (leaderboard(people=[{**PERSON, "name": "\t"}]), r"^data\.people\[0\]\.name: expected non-blank text$"),
            (leaderboard(people=[{**PERSON, "amount": " "}]), r"^data\.people\[0\]\.amount: expected non-blank text$"),
            (leaderboard(total={"amount": "", "pct": 1}), r"^data\.total\.amount: expected non-blank text$"),
            (leaderboard(title="W" * 25), r"^data\.title: expected at most 24 characters$"),
            (leaderboard(status="W" * 13), r"^data\.status: expected at most 12 characters$"),
            (leaderboard(people=[{**PERSON, "name": "W" * 25}]), r"^data\.people\[0\]\.name: expected at most 24"),
            (leaderboard(people=[{**PERSON, "amount": "$1,234K"}]), r"^data\.people\[0\]\.amount: expected at most 5"),
            (leaderboard(people=[{**PERSON, "amount": "１２３"}]), r"^data\.people\[0\]\.amount: expected digits, Latin"),
            (leaderboard(people=[{**PERSON, "amount": "$1 2"}]), r"^data\.people\[0\]\.amount: expected digits, Latin"),
            (leaderboard(total={"amount": "$12,345.6K", "pct": 1}), r"^data\.total\.amount: expected at most 8"),
            (leaderboard(people=[]), r"^data\.people: expected at least 1 item$"),
            (leaderboard(people=[PERSON] * 11), r"^data\.people: expected at most 10 items$"),
            (leaderboard(people=[{**PERSON, "pct": -1}]), r"^data\.people\[0\]\.pct: expected a number from 0 to 1000$"),
            (leaderboard(people=[{**PERSON, "pct": 1000.1}]), r"^data\.people\[0\]\.pct: expected a number from 0"),
            (leaderboard(people=[{**PERSON, "pct": "99%"}]), r"^data\.people\[0\]\.pct: expected number$"),
            (leaderboard(total={"amount": "$1M", "pct": None}), r"^data\.total\.pct: expected number$"),
            (leaderboard(people=[{**PERSON, "rank": 1}]), r"^data\.people\[0\]\.rank: unknown field$"),
        )
        for payload, pattern in cases:
            with self.subTest(pattern), self.assertRaisesRegex(TemplateError, pattern):
                render_template(self.page, payload)

    def test_widest_content_stays_inside_its_boxes(self):
        for name in ("W" * 24, "漢" * 24):
            with self.subTest(name[0]):
                image = render_template(self.page, widest(name))
                self.assertEqual(image.width, 384)
                self.assertLess(image.height, 4000)
                self.assertEqual(self.page.evaluate(OVERFLOW), [])
                self.assertEqual(len(self.page.query_selector_all("#receipt .rp-barrow")), 9)

    def test_fresh_page_renders_a_cyrillic_name(self):
        page = open_render_page(self.browser)
        try:
            name = "Щ. Шевченко-Жуковская"
            image = render_template(page, leaderboard(people=[{**PERSON, "name": name}] * 3))
            self.assertEqual(image.height, page.evaluate("Math.ceil(document.querySelector('#receipt').getBoundingClientRect().height)"))
            self.assertIn(name, page.inner_text("#receipt"))
        finally:
            page.close()

    def test_percent_is_floored_and_quota_needs_the_exact_pct(self):
        for pct, text, solid in ((99.6, "99%", False), (99.999, "99%", False), (100, "100%", True), (137.9, "137%", True), (0, "0%", False)):
            with self.subTest(pct):
                payload = leaderboard(people=[{**PERSON, "pct": pct}] * 2, total={"amount": "$1M", "pct": pct})
                bars = self.geometry(payload)["bars"]
                text_out = self.page.inner_text("#receipt")
                self.assertIn(f"{text} OF QUOTA", text_out)
                self.assertIn(f"$1M · {text}", text_out)
                self.assertEqual(bars[0][2], solid)

    def test_bars_scale_to_quota_on_whole_pixels(self):
        pcts = [137, 1000, 100, 99.6, 50, 0]
        geometry = self.geometry(leaderboard(people=[{**PERSON, "pct": pct} for pct in pcts]))
        track_left, track = geometry["tracks"][0]
        self.assertEqual((track_left, track), (152, 168))
        mark_centres = {left + width / 2 for left, width in geometry["marks"]}
        # The quota line is 75% along the track, under the QUOTA label's centre.
        self.assertEqual(mark_centres, {152 + 126})
        quota_left, quota_width = geometry["quota"]
        self.assertEqual(quota_left + quota_width / 2, 278)
        widths = [width for _, width, _ in geometry["bars"]]
        # A tone bar's 2px outline leaves a 4px hollow stub at 0%.
        self.assertEqual(widths, [168, 126, 125, 63, 4])
        for left, width, _ in geometry["bars"]:
            self.assertEqual((left, width), (round(left), round(width)))
        self.assertEqual([solid for *_, solid in geometry["bars"]], [True, True, False, False, False])

    def test_hero_alone_has_no_rows(self):
        render_template(self.page, leaderboard(people=[PERSON]))
        self.assertEqual(self.page.locator("#receipt .rp-barrow").count(), 0)
        self.assertEqual(self.page.locator("#receipt .micro").count(), 0)
        self.assertIn("99% OF QUOTA", self.page.inner_text("#receipt"))


if __name__ == "__main__":
    unittest.main()
