import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ticket_templates import TemplateError, open_render_page, render_template  # noqa: E402

SAMPLE = json.loads((ROOT / "samples" / "templates" / "agenda.json").read_text(encoding="utf-8"))
HAS_WEB = (ROOT / "web" / "node_modules").is_dir()

# Event boxes and the NOW line, relative to the timeline's top-left corner (the 08:00 line at 0).
_GEOMETRY_JS = """
() => {
  const absolute = [...document.querySelectorAll('#receipt *')].filter((el) => getComputedStyle(el).position === 'absolute');
  const timeline = absolute[0].parentElement.getBoundingClientRect();
  const box = (el) => { const r = el.getBoundingClientRect(); return [r.left - timeline.left, r.top - timeline.top, r.width, r.height]; };
  const events = absolute.filter((el) => getComputedStyle(el).overflow === 'hidden');
  const now = absolute.filter((el) => !events.includes(el) && el.getBoundingClientRect().height === 6);
  return {
    events: events.map((el) => ({ box: box(el), text: el.innerText, ink: getComputedStyle(el).backgroundColor === 'rgb(0, 0, 0)' })),
    now: now.map(box),
  };
}
"""

# Elements off whole-pixel positions (event boxes: off whole-pixel sizes too), wider than the paper, or clipping.
_FIT_JS = """
() => {
  const receipt = document.querySelector('#receipt'), origin = receipt.getBoundingClientRect();
  const fractional = [], outside = [], clipped = [];
  for (const el of receipt.querySelectorAll('*')) {
    const r = el.getBoundingClientRect(), style = getComputedStyle(el), name = `${el.tagName} "${el.textContent.slice(0, 20)}"`;
    const edges = [r.left - origin.left, r.top - origin.top, ...(style.position === 'absolute' ? [r.width, r.height] : [])];
    if (edges.some((v) => v % 1)) fractional.push(name);
    if (r.left < origin.left || r.right > origin.left + 384) outside.push(name);
    if (style.overflow !== 'visible' && (el.scrollWidth > el.clientWidth || el.scrollHeight > el.clientHeight)) clipped.push(name);
  }
  return { fractional, outside, clipped };
}
"""


def agenda(**data):
    payload = copy.deepcopy(SAMPLE)
    payload["data"].update(data)
    return payload


def event(start, end, title="Sync", kind="meeting"):
    return {"start": start, "end": end, "title": title, "kind": kind}


def worst(title, overlap):
    """12 events in a 14-hour day, every title at its 60-character limit."""
    events = []
    for index in range(12):
        start = 8 * 60 + index * 70
        end = start + (100 if overlap and index % 2 == 0 else 70)
        events.append(event(f"{start // 60:02d}:{start % 60:02d}", f"{end // 60:02d}:{end % 60:02d}", title * 60, "focus" if index % 3 else "meeting"))
    return agenda(date="W" * 12, dayStart=8, dayEnd=22, now="13:50", events=events)


def setUpModule():
    if HAS_WEB:
        subprocess.run(["npm", "run", "build"], cwd=ROOT / "web", check=True, capture_output=True)


@unittest.skipUnless(HAS_WEB, "needs web dependencies: make setup-web")
class AgendaTest(unittest.TestCase):
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

    def render(self, payload):
        image = render_template(self.page, payload)
        self.assertEqual(image.width, 384)
        self.assertEqual(self.page.evaluate(_FIT_JS), {"fractional": [], "outside": [], "clipped": []})
        return image

    def text(self):
        return self.page.evaluate("document.querySelector('#receipt').innerText")

    def geometry(self):
        return self.page.evaluate(_GEOMETRY_JS)

    def test_sample_is_strip_1g(self):
        self.render(SAMPLE)
        text = self.text()
        for expected in ("AGENDA", "THU 01 OCT", "5 EVENTS", "09:00 Standup", "10:00 FOCUS · billing migration",
                         "14:00 Design review", "NOW", "BUSY 5h", "FREE 5h"):
            self.assertIn(expected, text)
        self.assertNotIn("UNLABELLED", text)
        geometry = self.geometry()
        # 56 dots per hour from 08:00: 09:00-09:30 is 56..84, 14:00-15:00 is 336..392.
        self.assertEqual(geometry["events"][0]["box"], [36, 56, 348, 28])
        self.assertEqual([e["ink"] for e in geometry["events"]], [False, False, False, True, False])
        # 14:40 is 373.33 dots down: the 6-dot line centres on 373.
        self.assertIn([28, 370, 356, 6], geometry["now"])

    def test_worst_case_fits_under_the_length_limit(self):
        for name, payload in (
            ("W", worst("W", overlap=False)),
            ("CJK", worst("漢", overlap=False)),
            ("W overlapping", worst("W", overlap=True)),
            ("CJK overlapping", worst("漢", overlap=True)),
        ):
            with self.subTest(name):
                image = self.render(payload)
                self.assertLess(image.height, 4000)
                self.assertIn("12 EVENTS", self.text())

    def test_label_moves_below_when_it_does_not_fit_its_box(self):
        # A full-width meeting holds 33 Plex Mono cells: "09:00 " and 27 more.
        self.render(agenda(now=None, events=[event("09:00", "09:30", "W" * 27), event("10:00", "10:30", "W" * 28),
                                             event("11:00", "11:15", "Standup"), event("12:00", "12:30", "漢" * 16)]))
        labels = [e["text"] for e in self.geometry()["events"]]
        self.assertEqual(labels, ["09:00 " + "W" * 27, "", "", "12:00 " + "漢" * 16])
        text = self.text()
        self.assertIn("UNLABELLED", text)
        self.assertIn("10:00–10:30", text)
        self.assertIn("11:00–11:15", text)
        self.assertNotIn("09:00–09:30", text)

    def test_focus_plate_and_now_tag_fit_at_the_limit(self):
        # Focus: "13:00 FOCUS · " and 19 cells on the plate; current: 30 cells beside the NOW tag.
        self.render(agenda(now="15:30", events=[event("13:00", "14:00", "W" * 19, "focus"), event("15:00", "16:00", "W" * 24),
                                                event("16:00", "17:00", "W" * 20, "focus")]))
        labels = [e["text"] for e in self.geometry()["events"]]
        self.assertEqual(labels[0], "13:00 FOCUS · " + "W" * 19)
        self.assertTrue(labels[1].startswith("15:00 " + "W" * 24) and labels[1].endswith("NOW"), labels[1])
        self.assertEqual(labels[2], "")

    def test_overlapping_events_share_the_row(self):
        self.render(agenda(now="10:20", events=[event("10:00", "11:00", "A"), event("10:30", "12:00", "B"), event("11:00", "11:30", "C"),
                                                event("13:00", "14:00", "D")]))
        boxes = [e["box"] for e in self.geometry()["events"]]
        # A and C use the left lane, B the right; D overlaps nothing and spans the row.
        self.assertEqual(boxes, [[36, 112, 172, 56], [212, 140, 172, 84], [36, 168, 172, 28], [36, 280, 348, 56]])

    def test_a_third_concurrent_event_is_refused(self):
        payload = agenda(events=[event("10:00", "11:00"), event("10:30", "11:30"), event("10:45", "11:15")])
        with self.assertRaisesRegex(TemplateError, r"^data\.events\[2\]: overlaps two other events at 10:45; at most 2"):
            render_template(self.page, payload)

    def test_edges_round_to_the_nearest_dot(self):
        # 09:07 is 62.53 dots down, 09:08 is 63.47; 10:03 is 114.8.
        self.render(agenda(now=None, events=[event("09:07", "09:20"), event("09:20", "10:03")]))
        boxes = [e["box"] for e in self.geometry()["events"]]
        self.assertEqual(boxes, [[36, 63, 348, 75 - 63], [36, 75, 348, 115 - 75]])

    def test_busy_counts_overlaps_once(self):
        self.render(agenda(now=None, events=[event("09:00", "10:00"), event("09:30", "10:30"), event("12:00", "12:20")]))
        self.assertIn("BUSY 1h 50m", self.text())
        self.assertIn("FREE 8h 10m", self.text())

    def test_free_is_zero_only_when_the_day_is_full(self):
        for events, busy, free in (
            ([event("08:00", "08:59")], "BUSY 59m", "FREE 1m"),
            ([event("08:00", "08:30"), event("08:20", "09:00")], "BUSY 1h", "FREE 0m"),
            ([], "BUSY 0m", "FREE 1h"),
        ):
            with self.subTest(busy):
                self.render(agenda(dayStart=8, dayEnd=9, now=None, events=events))
                self.assertIn(busy, self.text())
                self.assertIn(free, self.text())

    def test_current_events_are_reversed(self):
        self.render(agenda(now="10:30", events=[event("10:00", "11:00", "A"), event("10:15", "10:45", "B"), event("11:00", "12:00", "C")]))
        self.assertEqual([e["ink"] for e in self.geometry()["events"]], [True, True, False])
        self.render(agenda(now="07:00", events=[event("10:00", "11:00", "A")]))
        geometry = self.geometry()
        self.assertEqual(geometry["now"], [])
        self.assertFalse(geometry["events"][0]["ink"])
        self.assertIn("1 EVENT\n", self.text())

    def test_cyrillic_title_renders_on_a_fresh_page(self):
        page = open_render_page(self.browser)
        try:
            image = render_template(page, agenda(events=[event("09:00", "10:00", "Планёрка отдела")]))
            self.assertEqual(image.width, 384)
            self.assertIn("Планёрка отдела", page.evaluate("document.querySelector('#receipt').innerText"))
        finally:
            page.close()

    def test_refuses_bad_data(self):
        cases = (
            (agenda(date=""), r"^data\.date: expected non-blank text$"),
            (agenda(date="  "), r"^data\.date: expected non-blank text$"),
            (agenda(date="W" * 13), r"^data\.date: expected at most 12 characters$"),
            (agenda(events=[event("09:00", "10:00", "")]), r"^data\.events\[0\]\.title: expected non-blank text$"),
            (agenda(events=[event("09:00", "10:00", " \t")]), r"^data\.events\[0\]\.title: expected non-blank text$"),
            (agenda(events=[event("09:00", "10:00", "W" * 61)]), r"^data\.events\[0\]\.title: expected at most 60"),
            (agenda(events=[event("9:00", "10:00")]), r"^data\.events\[0\]\.start: expected a time HH:MM from 00:00 to 23:59$"),
            (agenda(events=[event("09:60", "10:00")]), r"^data\.events\[0\]\.start: expected a time HH:MM"),
            (agenda(events=[event("24:00", "24:00")]), r"^data\.events\[0\]\.start: expected a time HH:MM"),
            (agenda(events=[event("09:00", "24:01")]), r"^data\.events\[0\]\.end: expected a time HH:MM from 00:00 to 24:00$"),
            (agenda(now="24:00"), r"^data\.now: expected a time HH:MM from 00:00 to 23:59$"),
            (agenda(events=[event("10:00", "10:00")]), r"^data\.events\[0\]\.end: expected at least 10 minutes after start$"),
            (agenda(events=[event("10:00", "09:00")]), r"^data\.events\[0\]\.end: expected at least 10 minutes after start$"),
            (agenda(events=[event("10:00", "10:09")]), r"^data\.events\[0\]\.end: expected at least 10 minutes after start$"),
            (agenda(events=[event("07:30", "09:00")]), r"^data\.events\[0\]: 07:30–09:00 is outside the day 08:00–18:00$"),
            (agenda(events=[event("17:30", "18:30")]), r"^data\.events\[0\]: 17:30–18:30 is outside the day 08:00–18:00$"),
            (agenda(events=[event("09:00", "09:30", kind="call")]), r'^data\.events\[0\]\.kind: expected "meeting" or "focus"$'),
            (agenda(events=[{**event("09:00", "09:30"), "where": "Room 2"}]), r"^data\.events\[0\]\.where: unknown field$"),
            (agenda(events=[event("09:00", "09:30")] * 13), r"^data\.events: expected at most 12 items$"),
            (agenda(dayStart=8, dayEnd=8), r"^data\.dayEnd: expected an hour after dayStart, at most 14 hours later$"),
            (agenda(dayStart=6, dayEnd=21), r"^data\.dayEnd: expected an hour after dayStart, at most 14 hours later$"),
            (agenda(dayStart=8.5), r"^data\.dayStart: expected a whole hour from 0 to 23$"),
            (agenda(dayEnd=25), r"^data\.dayEnd: expected a whole hour from 1 to 24$"),
        )
        for payload, pattern in cases:
            with self.subTest(pattern), self.assertRaisesRegex(TemplateError, pattern):
                render_template(self.page, payload)

    def test_day_can_end_at_midnight(self):
        self.render(agenda(dayStart=10, dayEnd=24, now="23:30", events=[event("23:00", "24:00", "Deploy")]))
        self.assertIn("23:00 Deploy", self.text())


if __name__ == "__main__":
    unittest.main()
