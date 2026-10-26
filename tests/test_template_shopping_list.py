import copy
import json
import sys
import unittest
from pathlib import Path

from tests.web_build import build_web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ticket_templates import (  # noqa: E402
    _FIT_JS, MAX_PAYLOAD_BYTES, PRINT_WIDTH_DOTS, TemplateError, open_render_page, render_template,
)

SHOPPING = json.loads((ROOT / "samples" / "templates" / "shopping-list.json").read_text(encoding="utf-8"))
ONE_METRE = 8000

# Clipped or overflowing text prints a wrong value while the render still succeeds.
_OVERFLOW_JS = """
() => [...document.querySelectorAll('#receipt, #receipt *')]
  .filter((el) => el.scrollWidth > el.clientWidth && el.clientWidth > 0 || el.getBoundingClientRect().right > 384)
  .map((el) => el.outerHTML.slice(0, 80))
"""
_TEXTS_JS = "(selector) => [...document.querySelectorAll('#receipt ' + selector)].map((el) => el.textContent)"
_LENGTH_REFUSAL = r"^the receipt would print [\d.]+ cm long; the limit is 100 cm$"


def setUpModule():
    build_web()


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

    def labels(self):
        return [label for label in self.texts(".rp-label") if label != "SEMANA"]

    def assert_in_order(self, expected):
        text = self.page.evaluate("() => document.querySelector('#receipt').textContent")
        at = 0
        for part in expected:
            found = text.find(part, at)
            self.assertNotEqual(found, -1, f"{part!r} missing or out of order")
            at = found + len(part)

    def test_every_item_amount_and_note_prints_in_the_order_sent(self):
        # A dropped list element still renders a print that looks complete.
        self.render(SHOPPING)
        items = [item for aisle in SHOPPING["data"]["aisles"] for item in aisle["items"]]
        self.assertEqual(len(self.texts(".rp-task")), len(items))
        self.assert_in_order([part for item in items for part in (item["name"], item["amount"], item.get("note", ""))])
        self.assert_in_order([recipe["name"] for recipe in SHOPPING["data"]["recipes"]] + SHOPPING["data"]["pantry"])

    def test_aisles_print_in_the_order_sent(self):
        # Reversed, so an alphabetical or catalogue re-sort would show.
        aisles = SHOPPING["data"]["aisles"][::-1]
        self.render(shopping(aisles=aisles))
        self.assertEqual(self.labels(), [aisle["name"] for aisle in aisles] + ["DESPENSA"])
        self.assert_in_order([item["name"] for aisle in aisles for item in aisle["items"]])

    def test_recipe_portions_are_singular_for_one(self):
        self.render(shopping(recipes=[{"name": "Arroz", "portions": 1}, {"name": "Feijão", "portions": 6}]))
        self.assertEqual(self.texts(".body")[:2], ["Arroz · 1 porção", "Feijão · 6 porções"])

    def test_item_without_note_has_no_meta_line(self):
        self.render(shopping(aisles=[{"name": "açougue", "items": [{"name": "bacon", "amount": "150 g"}]}]))
        self.assertEqual(self.texts(".rp-task-t"), ["bacon · 150 g"])
        self.assertEqual(self.texts(".rp-task-m"), [])

    def test_empty_pantry_omits_its_section(self):
        self.render(shopping(pantry=[]))
        self.assertNotIn("DESPENSA", self.labels())

    def test_pantry_only_prints_without_aisles(self):
        self.render(shopping(aisles=[], pantry=["sal", "azeite"]))
        self.assertEqual(self.labels(), ["DESPENSA"])
        self.assertEqual(self.texts(".rp-task"), [])
        self.assert_in_order(["sal", "azeite"])

    def test_typical_week_fits_half_a_metre(self):
        self.assertLess(self.render(SHOPPING).height, 4000)

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
                self.assertEqual(len(self.texts(".rp-task")), items)
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
