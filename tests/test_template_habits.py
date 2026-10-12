import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ticket_templates import TemplateError, open_render_page, render_template  # noqa: E402

SAMPLE = json.loads((ROOT / "samples" / "templates" / "habits.json").read_text(encoding="utf-8"))
HAS_WEB = (ROOT / "web" / "node_modules").is_dir()

READ = """() => {
  const receipt = document.querySelector('#receipt');
  const origin = receipt.getBoundingClientRect();
  const text = (selector) => [...receipt.querySelectorAll(selector)].map((node) => node.textContent);
  const rows = [...receipt.querySelectorAll('.rp-grid-row')].map((row) => [...row.querySelectorAll('.rp-cell')]
    .map((cell) => { const r = cell.getBoundingClientRect(); return [r.left - origin.left, r.right - origin.left]; }));
  return {
    sub: text('.rp-mast-sub')[0],
    labels: text('.rp-grid-l'),
    tiles: [...receipt.querySelectorAll('.rp-tile')].map((tile) => [...tile.children].map((node) => node.textContent)),
    ticks: [...(receipt.querySelector('.rp-grid')?.previousElementSibling?.children ?? [])].map((node) => node.textContent),
    rows,
    overflowing: [...receipt.querySelectorAll('*')].filter((node) => node.scrollWidth > node.clientWidth
      || node.getBoundingClientRect().right - origin.left > 384 || node.getBoundingClientRect().left < origin.left)
      .map((node) => node.className || node.tagName),
  };
}"""


def setUpModule():
    if HAS_WEB:
        subprocess.run(["npm", "run", "build"], cwd=ROOT / "web", check=True, capture_output=True)


def habits(*rows, **data):
    payload = copy.deepcopy(SAMPLE)
    payload["data"]["habits"] = [{"name": name, "days": days} for name, days in rows]
    payload["data"].update(data)
    return payload


@unittest.skipUnless(HAS_WEB, "needs web dependencies: make setup-web")
class HabitsTest(unittest.TestCase):
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

    def read(self, payload):
        image = render_template(self.page, payload)
        self.assertIsNotNone(image.convert("L").point(lambda value: 255 - value).getbbox(), "blank render")
        return self.page.evaluate(READ)

    def test_sample_counts_streak_and_completion(self):
        view = self.read(SAMPLE)
        self.assertEqual(view["sub"], "HABIT LOG · 30 DAYS")
        self.assertEqual([label[-5:] for label in view["labels"]], ["25/30", "11/30", "20/30", "16/30", "26/30"])
        # 98 done of 141 days that are not skipped: 69.5%.
        self.assertEqual(view["tiles"], [["BEST STREAK", "11 days", "Read 20 min"], ["COMPLETION", "70%", "▲ 6 pts vs Aug"]])
        self.assertEqual(view["overflowing"], [])

    def test_streak_ties_go_to_the_first_habit_and_skips_break_a_run(self):
        view = self.read(habits(("A", "1101" + "0" * 26), ("B", "0110" + "0" * 26), ("C", "11-11" + "0" * 25)))
        self.assertEqual(view["tiles"][0], ["BEST STREAK", "2 days", "A"])
        view = self.read(habits(("A", "1" + "0" * 29)))
        self.assertEqual(view["tiles"][0], ["BEST STREAK", "1 day", "A"])

    def test_skipped_days_leave_completion(self):
        view = self.read(habits(("A", "1" * 10 + "0" * 10 + "-" * 10), change={"points": -3, "vs": "Aug"}))
        self.assertEqual(view["tiles"][1], ["COMPLETION", "50%", "▼ 3 pts vs Aug"])

    def test_all_skipped_has_no_completion(self):
        view = self.read(habits(("A", "-" * 30), change=None))
        self.assertEqual(view["tiles"], [["BEST STREAK", "0 days"], ["COMPLETION", "—"]])

    def test_no_habits_still_renders(self):
        view = self.read(habits(change={"points": 0, "vs": "Aug"}))
        self.assertEqual(view["sub"], "HABIT LOG")
        self.assertEqual((view["labels"], view["rows"]), ([], []))
        self.assertEqual(view["tiles"], [["BEST STREAK", "0 days"], ["COMPLETION", "—", "0 pts vs Aug"]])

    def test_month_lengths_fill_the_width_on_whole_pixels(self):
        for length in (28, 31):
            with self.subTest(length):
                view = self.read(habits(("A", ("10-" * 11)[:length])))
                self.assertEqual(view["sub"], f"HABIT LOG · {length} DAYS")
                self.assertEqual(view["ticks"], ["1", "5", "10", "15", "20", "25", str(length)])
                cells = view["rows"][0]
                self.assertEqual(len(cells), length)
                self.assertEqual((cells[0][0], cells[-1][1]), (0, 384))
                self.assertTrue(all(float(edge).is_integer() for cell in cells for edge in cell), cells)

    def test_longest_payload_fits_the_paper(self):
        widest = "W" * 32
        view = self.read(habits(*[(widest, "1" * 31)] * 8, month="W" * 12, change={"points": -100, "vs": "W" * 10}))
        self.assertEqual(view["tiles"][0][1], "31 days")
        self.assertEqual(view["overflowing"], [])

    def test_invalid_data_names_the_field(self):
        for payload, pattern in (
            (habits(("A", "1" * 30), ("B", "1" * 31)), r"^data\.habits\[1\]\.days: expected 30 days, like habits\[0\]$"),
            (habits(("A", "1" * 27)), r"^data\.habits\[0\]\.days: expected 28 to 31 days of 1, 0 or -$"),
            (habits(("A", "1x" * 15)), r"^data\.habits\[0\]\.days: expected 28 to 31 days of 1, 0 or -$"),
            (habits(("A", "1" * 32)), r"^data\.habits\[0\]\.days: expected at most 31 characters$"),
            (habits(*[("A", "1" * 30)] * 9), r"^data\.habits: expected at most 8 items$"),
            (habits(("A" * 33, "1" * 30)), r"^data\.habits\[0\]\.name: expected at most 32 characters$"),
            (habits(month="M" * 13), r"^data\.month: expected at most 12 characters$"),
            (habits(change={"points": 1.5, "vs": "Aug"}), r"^data\.change\.points: expected a whole number from -100 to 100$"),
            (habits(change={"points": 101, "vs": "Aug"}), r"^data\.change\.points: expected a whole number from -100 to 100$"),
        ):
            with self.subTest(pattern), self.assertRaisesRegex(TemplateError, pattern):
                render_template(self.page, payload)


if __name__ == "__main__":
    unittest.main()
