import copy
import json
import re
import sys
import unittest
from datetime import datetime
from pathlib import Path

from tests.test_template_recipe import HEADLINE_JS, assert_stroke, capture
from tests.web_build import build_web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ticket_templates import (  # noqa: E402
    _FIT_JS, MAX_PAYLOAD_BYTES, PRINT_WIDTH_DOTS, TemplateError, open_render_page, render_template,
)

SHOPPING = json.loads((ROOT / "samples" / "templates" / "shopping-list.json").read_text(encoding="utf-8"))
ONE_METRE = 8000
NOW = datetime(2026, 10, 26, 14, 8)

# Clipped or overflowing text prints a wrong value while the render still succeeds.
_OVERFLOW_JS = """
() => [...document.querySelectorAll('#receipt, #receipt *')]
  .filter((el) => el.scrollWidth > el.clientWidth && el.clientWidth > 0 || el.getBoundingClientRect().right > 384)
  .map((el) => el.outerHTML.slice(0, 80))
"""
_TEXTS_JS = "(selector) => [...document.querySelectorAll('#receipt ' + selector)].map((el) => el.textContent)"
# Line boxes of each element's text: 1 means it did not wrap.
_LINES_JS = """(selector) => [...document.querySelectorAll('#receipt ' + selector)].map((el) => {
  const range = document.createRange();
  range.selectNodeContents(el);
  return new Set([...range.getClientRects()].map((rect) => rect.top)).size;
})"""
_EDGES_JS = """() => [...document.querySelectorAll('#receipt .kr-box, #receipt .kr-chip, #receipt .kr-pantry, #receipt .kr-menu, #receipt .kr-aisle')]
  .map((el) => el.getBoundingClientRect()).map((r) => [r.left, r.right, r.top, r.bottom])"""
_LENGTH_REFUSAL = r"^the receipt would print [\d.]+ cm long; the limit is 100 cm$"


def setUpModule():
    build_web()


def glue(text):
    return re.sub(r"(\d[\d.,/]*|[½¼¾≈×])\s+", "\\1\u00a0", text)


def display(name):
    glued = glue(name)
    return glued[:1].upper() + glued[1:]


def shopping(**data):
    payload = copy.deepcopy(SHOPPING)
    payload["data"].update(data)
    return payload


def maximal(glyph, items=160):
    """Every string at its cap and every list at its cap, with ``items`` items over the 8 aisles."""
    item = {"name": glyph * 90, "amount": glyph * 16, "note": glyph * 52}
    return shopping(
        recipes=[{"name": glyph * 64, "portions": 99}] * 14,
        aisles=[{"name": glyph * 30, "items": [item] * (items // 8 + (index < items % 8))} for index in range(8)],
        pantry=[glyph * 40] * 42,
    )


def one_dot_share(image, boxes):
    """The share of horizontal black runs one dot wide inside ``boxes``: thin stems print broken."""
    runs = []
    for left, top, right, bottom in ((round(value) for value in box) for box in boxes):
        for y in range(top, bottom):
            row = [image.getpixel((x, y)) == 0 for x in range(left, right)] + [False]
            length = 0
            for black in row:
                if black:
                    length += 1
                elif length:
                    runs.append(length)
                    length = 0
    return runs.count(1) / len(runs)


def largest(glyph):
    """``maximal`` with as many items as the payload byte limit lets reach the page."""
    items = 160
    while len(json.dumps(maximal(glyph, items), ensure_ascii=False).encode()) > MAX_PAYLOAD_BYTES:
        items -= 1
    return maximal(glyph, items), items


class ShoppingListTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright

        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)
        cls.page = open_render_page(cls.browser)
        cls.page.clock.set_fixed_time(NOW)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def render(self, payload, **limits):
        image = render_template(self.page, payload, **limits)
        self.assertEqual(self.page.evaluate(_OVERFLOW_JS), [])
        return image

    def texts(self, selector):
        return self.page.evaluate(_TEXTS_JS, selector)

    def assert_whole_edges(self):
        edges = self.page.evaluate(_EDGES_JS)
        self.assertTrue(edges)
        for edge in edges:
            self.assertTrue(all(float(value).is_integer() for value in edge), edge)

    def test_every_item_amount_and_note_prints_in_the_order_sent(self):
        # A dropped list element still renders a print that looks complete.
        self.render(SHOPPING)
        items = [item for aisle in SHOPPING["data"]["aisles"] for item in aisle["items"]]
        self.assertTrue(any("note" in item for item in items))
        self.assertEqual(self.texts(".kr-item-name"),
                         [display(item["name"]) + (f" · {glue(item['note'])}" if "note" in item else "") for item in items])
        self.assertEqual(self.texts(".kr-amount"), [item["amount"] for item in items])
        self.assertEqual([text[2:] for text in self.texts(".kr-menu")],
                         [f"{glue(recipe['name'])}{recipe['portions']} {'porção' if recipe['portions'] == 1 else 'porções'}" for recipe in SHOPPING["data"]["recipes"]])
        self.assertEqual(self.texts(".kr-chip"), [display(name) for name in SHOPPING["data"]["pantry"]])

    def test_aisles_and_items_print_in_the_order_sent(self):
        # Reversed, so an alphabetical or catalogue re-sort would show.
        aisles = [{**aisle, "items": aisle["items"][::-1]} for aisle in SHOPPING["data"]["aisles"][::-1]]
        self.render(shopping(aisles=aisles))
        self.assertEqual(self.texts(".kr-aisle"), [aisle["name"] for aisle in aisles])
        self.assertEqual(self.texts(".kr-amount"), [item["amount"] for aisle in aisles for item in aisle["items"]])

    def test_menu_numbers_recipes_and_portions_are_singular_for_one(self):
        self.render(shopping(recipes=[{"name": "Arroz", "portions": 1}, {"name": "Feijão", "portions": 6}]))
        self.assertEqual(self.texts(".kr-portions"), ["1 porção", "6 porções"])
        self.assertEqual(self.texts(".kr-menu"), ["01Arroz1 porção", "02Feijão6 porções"])

    def test_summary_counts_recipes_items_and_aisles(self):
        self.render(SHOPPING)
        data = SHOPPING["data"]
        items = sum(len(aisle["items"]) for aisle in data["aisles"])
        self.assertEqual(self.texts(".kr-summary"), [f"{len(data['recipes'])} receitas · {items} itens · {len(data['aisles'])} corredores"])
        self.render(shopping(recipes=[{"name": "Arroz", "portions": 2}], aisles=[{"name": "mercearia", "items": [{"name": "arroz", "amount": "1 kg"}]}]))
        self.assertEqual(self.texts(".kr-summary"), ["1 receita · 1 item · 1 corredor"])

    def test_item_without_note_prints_its_name_only(self):
        self.render(shopping(aisles=[{"name": "açougue", "items": [{"name": "bacon", "amount": "150 g"}]}]))
        self.assertEqual(self.texts(".kr-item-name"), ["Bacon"])
        self.assertEqual(self.texts(".kr-note"), [])

    def test_names_print_capitalized_with_numbers_glued_to_their_unit(self):
        self.render(shopping(aisles=[{"name": "mercearia", "items": [{"name": "massa de 2 ovos", "amount": "1 un", "note": "3 × lata"}]}],
                             pantry=["óleo", "½ maço de salsa"]))
        self.assertEqual(self.texts(".kr-item-name"), ["Massa de 2\u00a0ovos · 3\u00a0×\u00a0lata"])
        self.assertEqual(self.texts(".kr-chip"), ["Óleo", "½\u00a0maço de salsa"])

    def test_amounts_and_portions_never_wrap(self):
        # A long name beside "200 ml" once pushed "ml" onto a line of its own.
        long = "creme de leite fresco com teor de gordura acima de trinta e cinco por cento, gelado"
        self.render(shopping(
            recipes=[{"name": "Pappardelle fresco ao funghi secchi com manteiga noisette", "portions": 99}],
            aisles=[{"name": "refrigerados", "items": [{"name": long, "amount": "200 ml"}, {"name": long, "amount": "1,25 kg (aprox.)", "note": long[:52]}]}],
        ))
        for selector in (".kr-amount", ".kr-portions"):
            with self.subTest(selector):
                self.assertEqual(set(self.page.evaluate(_LINES_JS, selector)), {1})

    def test_empty_pantry_omits_its_box(self):
        self.render(shopping(pantry=[]))
        self.assertEqual(self.texts(".kr-pantry"), [])

    def test_pantry_only_prints_without_aisles(self):
        self.render(shopping(aisles=[], pantry=["sal", "azeite"]))
        self.assertEqual(self.texts(".kr-aisle"), [])
        self.assertEqual(self.texts(".kr-item"), [])
        self.assertEqual(self.texts(".kr-chip"), ["Sal", "Azeite"])
        self.assertTrue(self.texts(".kr-summary")[0].endswith(" · 0 itens · 0 corredores"))

    def boxes(self, selector):
        return self.page.evaluate("(selector) => [...document.querySelectorAll('#receipt ' + selector)]"
                                  ".map((el) => { const r = el.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; })", selector)

    def test_title_fits_on_one_line_at_one_size(self):
        self.render(SHOPPING)
        headline = self.page.evaluate(HEADLINE_JS)
        self.assertEqual(headline["words"][0]["lines"], 1, "COMPRAS split across lines")
        self.assertLessEqual(headline["words"][0]["right"], PRINT_WIDTH_DOTS)
        self.assertEqual(len(headline["sizes"]), 1)
        self.assertLess(float(headline["sizes"][0][:-2]), 108)

    def test_notes_print_with_stems_as_heavy_as_the_amounts(self):
        # Archivo 600 at 62% printed a third of its runs one dot wide; the bold mono amounts print about a tenth.
        image = self.render(SHOPPING)
        self.assertLessEqual(one_dot_share(image, self.boxes(".kr-note")), one_dot_share(image, self.boxes(".kr-amount")))

    def test_note_separator_prints_a_solid_dot(self):
        image = self.render(SHOPPING)
        separators = self.boxes(".kr-note-sep")
        self.assertTrue(separators)
        for left, top, right, bottom in ((round(value) for value in box) for box in separators):
            solid = any(all(image.getpixel((x + dx, y + dy)) == 0 for dx in (0, 1) for dy in (0, 1))
                        for x in range(left, right - 1) for y in range(top, bottom - 1))
            self.assertTrue(solid, "the separator dot is thinner than 2x2 dots")

    def test_strokes_keep_their_width(self):
        # Before the print profile trims the bottom dot of tall runs against heat smear.
        image = capture(self.page, SHOPPING)
        for left, top, right, bottom in self.boxes(".rp-rule-bar"):
            assert_stroke(self, image, 200, int(top), 8)
        (left, top, right, bottom), = self.boxes(".kr-pantry")
        assert_stroke(self, image, 200, int(top), 4)
        assert_stroke(self, image, 200, int(bottom) - 4, 4)

    def test_footer_prints_the_render_time(self):
        self.render(SHOPPING)
        self.assertEqual(self.texts(".kr-printed"), ["impresso em 26 out 2026 · 14:08"])

    def test_typical_week_fits_half_a_metre(self):
        self.assertLess(self.render(SHOPPING).height, 4000)

    def test_checkboxes_and_boxes_sit_on_whole_pixels(self):
        # A fractional edge smears a 3px stroke over four dot columns.
        for payload in (SHOPPING, largest("W")[0], largest("漢")[0]):
            with self.subTest(payload["data"]["recipes"][0]["name"][:8]):
                try:
                    render_template(self.page, payload, max_height_dots=ONE_METRE)
                except TemplateError as error:
                    self.assertRegex(str(error), _LENGTH_REFUSAL)
                self.assert_whole_edges()

    def test_maximal_payload_fits_the_paper_and_is_refused_for_length(self):
        # The caps allow more than 1 m; the length guard must refuse it, never clip it. In CJK the
        # byte limit refuses 160 items at their caps first, so the largest payload it passes stands in.
        for glyph in ("W", "漢"):
            with self.subTest(glyph):
                payload, items = largest(glyph)
                with self.assertRaisesRegex(TemplateError, _LENGTH_REFUSAL):
                    render_template(self.page, payload, max_height_dots=ONE_METRE)
                self.assertIsNone(self.page.evaluate(_FIT_JS, [PRINT_WIDTH_DOTS, 1]))
                self.assertEqual(self.page.evaluate(_OVERFLOW_JS), [])
                self.assertEqual(len(self.texts(".kr-item")), items)
                self.assertEqual(len(self.texts(".kr-chip")), 42)
        self.assertEqual(largest("W")[1], 160)

    def test_bad_data_is_refused(self):
        item = {"name": "sal", "amount": "1 kg"}
        aisle = {"name": "mercearia", "items": [item]}
        for data, pattern in (
            ({"extra": 1}, r"^data\.extra: unknown field$"),
            ({"aisles": [{**aisle, "items": [{**item, "kind": "base"}]}]}, r"^data\.aisles\[0\]\.items\[0\]\.kind: unknown field$"),
            ({"aisles": [], "pantry": []}, r"^data: expected an aisle or a pantry item$"),
            ({"recipes": []}, r"^data\.recipes: expected at least 1 item$"),
            ({"aisles": [{**aisle, "items": []}]}, r"^data\.aisles\[0\]\.items: expected at least 1 item$"),
            ({"recipes": [{"name": " ", "portions": 2}]}, r"^data\.recipes\[0\]\.name: expected non-blank text$"),
            ({"aisles": [{**aisle, "name": ""}]}, r"^data\.aisles\[0\]\.name: expected non-blank text$"),
            ({"aisles": [{**aisle, "items": [{**item, "amount": "​"}]}]}, r"^data\.aisles\[0\]\.items\[0\]\.amount: expected non-blank text$"),
            ({"pantry": ["  "]}, r"^data\.pantry\[0\]: expected non-blank text$"),
            ({"recipes": [{"name": "W" * 65, "portions": 2}]}, r"^data\.recipes\[0\]\.name: expected at most 64 characters$"),
            ({"aisles": [{**aisle, "name": "W" * 31}]}, r"^data\.aisles\[0\]\.name: expected at most 30 characters$"),
            ({"aisles": [{**aisle, "items": [{**item, "name": "W" * 91}]}]}, r"^data\.aisles\[0\]\.items\[0\]\.name: expected at most 90 characters$"),
            ({"aisles": [{**aisle, "items": [{**item, "amount": "W" * 17}]}]}, r"^data\.aisles\[0\]\.items\[0\]\.amount: expected at most 16 characters$"),
            ({"aisles": [{**aisle, "items": [{**item, "note": "W" * 53}]}]}, r"^data\.aisles\[0\]\.items\[0\]\.note: expected at most 52 characters$"),
            ({"pantry": ["W" * 41]}, r"^data\.pantry\[0\]: expected at most 40 characters$"),
            ({"recipes": [{"name": "Arroz", "portions": 0}]}, r"^data\.recipes\[0\]\.portions: expected a whole number from 1 to 99$"),
            ({"recipes": [{"name": "Arroz", "portions": 2}] * 15}, r"^data\.recipes: expected at most 14 items$"),
            ({"aisles": [aisle] * 9}, r"^data\.aisles: expected at most 8 items$"),
            ({"pantry": ["sal"] * 43}, r"^data\.pantry: expected at most 42 items$"),
            ({"aisles": [{**aisle, "items": [item] * 161}]}, r"^data\.aisles\[0\]\.items: expected at most 160 items$"),
            ({"aisles": [{**aisle, "items": [item] * 21}] * 8}, r"^data\.aisles: expected at most 160 items across all aisles$"),
        ):
            with self.subTest(data), self.assertRaisesRegex(TemplateError, pattern):
                render_template(self.page, shopping(**data))

    def test_wrong_schema_version_is_refused(self):
        with self.assertRaisesRegex(TemplateError, r'^template "shopping-list" expects schemaVersion 1, got 2$'):
            render_template(self.page, {**SHOPPING, "schemaVersion": 2})


if __name__ == "__main__":
    unittest.main()
