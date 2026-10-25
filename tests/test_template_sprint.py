import copy
import json
import sys
import unittest
from pathlib import Path

from tests.web_build import build_web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ticket_templates import TemplateError, open_render_page, render_template  # noqa: E402

SAMPLE = json.loads((ROOT / "samples" / "templates" / "sprint.json").read_text(encoding="utf-8"))


def widest(glyph):
    """Every list full and every string at its limit, in one of the widest glyphs."""
    card = {"id": glyph * 12, "title": glyph * 24}
    return {
        "template": "sprint",
        "schemaVersion": 1,
        "data": {
            "sprint": glyph * 12,
            "day": 99,
            "of": 99,
            "date": glyph * 12,
            "columns": [{"name": glyph * 10, "cards": [card] * 6}] * 6,
        },
    }


# Every box inside the 384-dot layout height, and no box hiding its text.
OVERFLOW = """() => {
  const receipt = document.querySelector('#receipt'), top = receipt.getBoundingClientRect().top;
  return [...receipt.querySelectorAll('*')]
    .filter((el) => el.scrollWidth > el.clientWidth || el.getBoundingClientRect().bottom - top > 384)
    .map((el) => el.outerHTML.slice(0, 80));
}"""

GEOMETRY = """() => {
  const receipt = document.querySelector('#receipt'), origin = receipt.getBoundingClientRect();
  const box = (el) => { const r = el.getBoundingClientRect(); return [r.left - origin.left, r.top - origin.top, r.width, r.height]; };
  return {
    receipt: [receipt.offsetWidth, receipt.offsetHeight],
    cards: [...receipt.querySelectorAll('.meta-strong[style*="border"]')].map(box),
  };
}"""


def sprint(**data):
    payload = copy.deepcopy(SAMPLE)
    payload["data"].update(data)
    return payload


def column(name="TODO", cards=None):
    return {"name": name, "cards": [{"id": "A-1", "title": "x"}] if cards is None else cards}


def setUpModule():
    build_web()


class SprintTest(unittest.TestCase):
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

    def test_refuses_bad_data(self):
        card = {"id": "A-1", "title": "x"}
        cases = []
        for field in ("sprint", "date"):
            for blank in ("", "   "):
                cases.append((sprint(**{field: blank}), rf"^data\.{field}: expected non-blank text$"))
        for blank in ("", " \t"):
            cases += [
                (sprint(columns=[column(name=blank)]), r"^data\.columns\[0\]\.name: expected non-blank text$"),
                (sprint(columns=[column(cards=[{"id": blank, "title": "x"}])]), r"^data\.columns\[0\]\.cards\[0\]\.id: expected non-blank text$"),
                (sprint(columns=[column(cards=[{"id": "A-1", "title": blank}])]), r"^data\.columns\[0\]\.cards\[0\]\.title: expected non-blank text$"),
            ]
        cases += [
            (sprint(sprint="W" * 13), r"^data\.sprint: expected at most 12 characters$"),
            (sprint(date="W" * 13), r"^data\.date: expected at most 12 characters$"),
            (sprint(columns=[column(name="W" * 11)]), r"^data\.columns\[0\]\.name: expected at most 10 characters$"),
            (sprint(columns=[column(cards=[{"id": "W" * 13, "title": "x"}])]), r"^data\.columns\[0\]\.cards\[0\]\.id: expected at most 12"),
            (sprint(columns=[column(cards=[{"id": "A-1", "title": "W" * 25}])]), r"^data\.columns\[0\]\.cards\[0\]\.title: expected at most 24"),
            (sprint(columns=[]), r"^data\.columns: expected at least 1 item$"),
            (sprint(columns=[column()] * 7), r"^data\.columns: expected at most 6 items$"),
            (sprint(columns=[column(cards=[card] * 7)]), r"^data\.columns\[0\]\.cards: expected at most 6 items$"),
            (sprint(columns=[{"name": "TODO"}]), r"^data\.columns\[0\]\.cards: expected array$"),
            (sprint(columns=[column(cards=[{**card, "owner": "me"}])]), r"^data\.columns\[0\]\.cards\[0\]\.owner: unknown field$"),
        ]
        for field in ("day", "of"):
            for bad in (0, 100, 1.5, "6", True):
                cases.append((sprint(**{field: bad}), rf"^data\.{field}: expected a whole number from 1 to 99$"))
        for payload, pattern in cases:
            with self.subTest(pattern), self.assertRaisesRegex(TemplateError, pattern):
                render_template(self.page, payload)

    def test_widest_content_fits_the_paper(self):
        # The fit guard refuses clipped text and boxes past the 384-dot paper edge.
        for glyph in ("W", "漢"):
            with self.subTest(glyph):
                image = render_template(self.page, widest(glyph))
                self.assertEqual((image.mode, image.width), ("1", 384))
                self.assertLess(image.height, 4000)
                self.assertEqual(self.page.evaluate(OVERFLOW), [])

    def test_counts_are_derived_from_the_cards(self):
        render_template(self.page, SAMPLE)
        text = self.page.inner_text("#receipt")
        self.assertIn("DAY 6 / 10", text)
        self.assertIn("13 ITEMS", text)
        heads = self.page.locator("#receipt .label").all_inner_texts()
        self.assertEqual([head.split() for head in heads],
                         [["BACKLOG", "4"], ["DOING", "3"], ["REVIEW", "2"], ["DONE", "4"]])
        render_template(self.page, sprint(columns=[column(cards=[]), column()]))
        self.assertIn("1 ITEM\n", self.page.inner_text("#receipt"))
        self.assertEqual(self.page.locator("#receipt .label").first.inner_text().split(), ["TODO", "0"])

    def test_cards_flow_into_stacks_of_three_on_whole_pixels(self):
        render_template(self.page, sprint(columns=[column(cards=[{"id": f"A-{n}", "title": "x"} for n in range(4)])]))
        geometry = self.page.evaluate(GEOMETRY)
        self.assertEqual(geometry["receipt"][1], 384)
        cards = geometry["cards"]
        for card in cards:
            self.assertEqual(card, [round(value) for value in card])
            self.assertEqual(card[2], 240)
        lefts = [card[0] for card in cards]
        self.assertEqual(lefts[:3], [lefts[0]] * 3)
        self.assertEqual(lefts[3], lefts[0] + 240 + 12)
        self.assertEqual(cards[3][1], cards[0][1])

    def test_fresh_page_renders_a_cyrillic_title(self):
        page = open_render_page(self.browser)
        try:
            payload = sprint(sprint="СПРИНТ 24",
                             columns=[column(cards=[{"id": "Ш" * 12, "title": "Ш" * 24}] * 6)])
            image = render_template(page, payload)
            self.assertEqual(image.width, 384)
            self.assertEqual(page.evaluate(OVERFLOW), [])
        finally:
            page.close()

    def test_sprint_block_prints_first_and_column_heads_on_the_right(self):
        image = render_template(self.page, SAMPLE)
        self.assertEqual(image.width, 384)
        # Turned clockwise: the layout's left edge (the ink sprint block, 150 dots) is the start of the
        # strip, its top edge (the column heads) is the right edge, and the feed comes last.
        self.assertEqual({image.getpixel((x, y)) for x in (2, 191, 381) for y in (2, 147)}, {0}, "sprint block not first")
        self.assertEqual({image.getpixel((x, 155)) for x in range(384)}, {255}, "gap after the sprint block")
        # The first head's 6-dot underline: layout rows 28-33 from x 170, image columns 383-33..383-28.
        self.assertEqual({image.getpixel((x, y)) for x in range(351, 355) for y in range(175, 400)}, {0}, "head underline")
        self.assertIsNone(image.crop((0, image.height - 56, 384, image.height)).convert("L")
                          .point(lambda value: 255 - value).getbbox(), "feed not at the end")


if __name__ == "__main__":
    unittest.main()
