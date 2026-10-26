import copy
import json
import sys
import unittest
from pathlib import Path

from tests.web_build import build_web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ticket_templates import _FIT_JS, PRINT_WIDTH_DOTS, TemplateError, open_render_page, render_template  # noqa: E402

RECIPE = json.loads((ROOT / "samples" / "templates" / "recipe.json").read_text(encoding="utf-8"))
ONE_METRE = 8000

# The longest print in the mise-en-place catalogue (2026-10, 60 recipes): 4182 dots.
MADALENA = {"template": "recipe", "schemaVersion": 1, "data": {
    "name": "Torta madalena", "portions": 4,
    "groups": [
        {"name": "Purê", "items": [
            {"name": "Batata (asterix ou monalisa)", "amount": "1 kg"}, {"name": "Leite", "amount": "300 ml"},
            {"name": "Parmesão em peça", "amount": "19,8 g"}, {"name": "Manteiga", "amount": "28,5 g"},
            {"name": "Folha de louro", "amount": "1 folha"}, {"name": "Noz-moscada", "amount": "a gosto"},
            {"name": "Sal", "amount": "a gosto"}]},
        {"name": "Recheio", "items": [
            {"name": "Carne moída (patinho)", "amount": "500 g"}, {"name": "Cebola", "amount": "1 un"},
            {"name": "Cenoura", "amount": "150 g"}, {"name": "Alho", "amount": "2 dentes"},
            {"name": "Filé de anchova", "amount": "3 un"}, {"name": "Ervilha congelada", "amount": "80,4 g"},
            {"name": "Extrato de tomate", "amount": "33 g"}, {"name": "Farinha de trigo", "amount": "15 g"},
            {"name": "Shoyu", "amount": "15 ml"}, {"name": "Vinagre de vinho", "amount": "15 ml"},
            {"name": "Tomilho", "amount": "0,2 maço"}, {"name": "Cravo em pó", "amount": "a gosto"},
            {"name": "Azeite", "amount": "22,5 ml"}, {"name": "Sal", "amount": "a gosto"},
            {"name": "Pimenta-do-reino moída", "amount": "a gosto"}, {"name": "Parmesão em peça", "amount": "a gosto"}]},
    ],
    "phases": [
        {"name": "Purê", "steps": [
            {"verb": "Cozinhe as batatas", "time": "20 min", "text": "Em pedaços médios, cobertas de água, com 1 colher (chá) de sal e o louro. Ferveu, fogo médio."},
            {"verb": "Reserve a água", "time": "2 min", "text": "Guarde 2 xícaras da água do cozimento para o recheio e escorra as batatas."},
            {"verb": "Aqueça o leite", "time": "1 min", "text": "No micro-ondas."},
            {"verb": "Esprema as batatas", "time": "3 min", "text": "Ainda quentes, sobre a panela seca."},
            {"verb": "Finalize o purê", "time": "5 min", "text": "Fogo médio, leite aos poucos com o batedor de arame, depois a manteiga. Fora do fogo, queijo e noz-moscada."}]},
        {"name": "Recheio", "steps": [
            {"verb": "Preaqueça o forno", "time": "10 min", "text": "Unte com azeite um refratário de 30 × 20 cm."},
            {"verb": "Prepare os legumes", "time": "8 min", "text": "Cenoura no ralo fino, cebola e alho picados fino, tomilho debulhado."},
            {"verb": "Doure a carne", "time": "10 min", "text": "1 colher (sopa) de azeite, uma pitada de sal e a farinha polvilhada, até a farinha dourar. Reserve."},
            {"verb": "Refogue os legumes", "time": "6 min", "text": "½ colher (sopa) de azeite: cebola até murchar, cenoura por 2 min, alho e anchova por 1 min."},
            {"verb": "Deglaceie", "time": "4 min", "text": "Extrato, depois a água das batatas, raspando o fundo. Shoyu, vinagre e cravo até ferver."},
            {"verb": "Cozinhe o recheio", "time": "10 min", "text": "Carne de volta, ervilha e tomilho. Fogo baixo, mexendo de vez em quando, até encorpar."}]},
        {"name": "Montagem", "steps": [
            {"verb": "Monte a torta", "time": "5 min", "text": "Recheio no refratário, purê por cima com as costas da colher. Risque com o garfo e polvilhe queijo."},
            {"verb": "Asse", "time": "20 min", "text": "Até dourar. Sirva a seguir."}]},
    ],
}}

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


def recipe(**data):
    payload = copy.deepcopy(RECIPE)
    payload["data"].update(data)
    for key in [key for key, value in data.items() if value is None]:
        del payload["data"][key]
    return payload


def maximal(glyph):
    """Every string at its cap and every list at its cap or total."""
    item = {"name": glyph * 90, "amount": glyph * 16, "kind": "base"}
    step = {"verb": glyph * 40, "time": glyph * 28, "text": glyph * 210}
    return recipe(
        name=glyph * 64, portions=99,
        groups=[{"name": glyph * 48, "items": [item] * 6}] * 5 + [{"name": glyph * 48, "items": [item] * 5}],
        phases=[{"name": glyph * 28, "steps": [step] * 4}] * 6 + [{"name": glyph * 28, "steps": [step] * 3}],
    )


class RecipeTest(unittest.TestCase):
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

    def assert_in_order(self, expected):
        text = self.page.evaluate("() => document.querySelector('#receipt').textContent")
        at = 0
        for part in expected:
            found = text.find(part, at)
            self.assertNotEqual(found, -1, f"{part!r} missing or out of order")
            at = found + len(part)

    def test_every_ingredient_and_amount_prints_in_the_order_sent(self):
        # A dropped list element still renders a print that looks complete.
        self.render(RECIPE)
        items = [item for group in RECIPE["data"]["groups"] for item in group["items"]]
        self.assertEqual(len(self.texts(".rp-task")), len(items))
        self.assert_in_order([part for item in items for part in (item["name"], item.get("amount", ""))])

    def test_steps_number_continuously_across_phases(self):
        self.render(RECIPE)
        steps = [step for phase in RECIPE["data"]["phases"] for step in phase["steps"]]
        self.assertEqual(self.texts(".rp-step-n"), [str(n) for n in range(1, len(steps) + 1)])
        self.assert_in_order([part for step in steps for part in (step["verb"], step["text"])])
        self.assertEqual(self.texts(".rp-step-body b"), [step["verb"] for step in steps])

    def test_kind_labels_mark_exactly_those_items(self):
        self.render(RECIPE)
        items = [item for group in RECIPE["data"]["groups"] for item in group["items"]]
        for title, item in zip(self.texts(".rp-task-t"), items):
            with self.subTest(item["name"]):
                self.assertEqual(title.endswith(" (opcional)"), item.get("kind") == "optional")
                self.assertEqual(title.endswith(" (receita base)"), item.get("kind") == "base")
        text = self.page.evaluate("() => document.querySelector('#receipt').textContent")
        self.assertEqual(text.count("(opcional)"), 1)
        self.assertEqual(text.count("(receita base)"), 1)

    def test_named_groups_and_phases_print_sub_headings(self):
        self.render(RECIPE)
        names = [group["name"] for group in RECIPE["data"]["groups"]] + [phase["name"] for phase in RECIPE["data"]["phases"]]
        self.assertEqual(self.texts(".body-strong"), names)

    def test_one_unnamed_group_prints_no_sub_heading(self):
        self.render(recipe(groups=[{"items": [{"name": "arroz", "amount": "200 g"}, {"name": "sal", "amount": "a gosto"}]}], phases=None))
        self.assertEqual(self.texts(".body-strong"), [])
        self.assertEqual(self.texts(".rp-task-t"), ["arroz · 200 g", "sal · a gosto"])

    def test_steps_section_is_omitted_without_phases(self):
        for phases in (None, []):
            with self.subTest(phases=phases):
                self.render(recipe(phases=phases))
                self.assertNotIn("PASSOS", self.texts(".rp-label"))
                self.assertEqual(self.texts(".rp-step"), [])

    def test_item_without_amount_prints_its_name_only(self):
        self.render(recipe(groups=[{"items": [{"name": "salsinha picada"}]}]))
        self.assertEqual(self.texts(".rp-task-t"), ["salsinha picada"])

    def test_step_without_text_prints_its_verb(self):
        self.render(recipe(phases=[{"steps": [{"verb": "Sirva"}]}]))
        self.assertEqual(self.texts(".rp-step-body > div:first-child"), ["Sirva"])

    def test_timer_boxes_sit_on_whole_pixels(self):
        # A fractional edge smears the 2px border over three dot columns.
        for payload in (RECIPE, MADALENA, maximal("W"), maximal("漢")):
            with self.subTest(payload["data"]["name"][:8]):
                try:
                    render_template(self.page, payload, max_height_dots=ONE_METRE)
                except TemplateError as error:
                    self.assertRegex(str(error), _LENGTH_REFUSAL)
                edges = self.page.evaluate("""() => [...document.querySelectorAll('#receipt .rp-step-timer')]
                    .map((el) => el.getBoundingClientRect()).map((r) => [r.left, r.right, r.top, r.bottom])""")
                self.assertTrue(edges)
                for edge in edges:
                    self.assertTrue(all(float(value).is_integer() for value in edge), edge)

    def test_portions_are_singular_for_one(self):
        for portions, expected in ((1, "1 PORÇÃO"), (4, "4 PORÇÕES"), (99, "99 PORÇÕES")):
            with self.subTest(portions):
                self.render(recipe(portions=portions))
                self.assertEqual(self.texts(".rp-bar span")[1], expected)

    def test_longest_real_recipe_fits_one_metre(self):
        image = self.render(MADALENA, max_height_dots=ONE_METRE)
        self.assertLess(image.height, ONE_METRE)

    def test_maximal_payload_fits_the_paper_and_is_refused_for_length(self):
        # The caps allow more than 1 m; the length guard must refuse it, never clip it.
        for glyph in ("W", "漢"):
            with self.subTest(glyph):
                with self.assertRaisesRegex(TemplateError, _LENGTH_REFUSAL):
                    render_template(self.page, maximal(glyph), max_height_dots=ONE_METRE)
                self.assertIsNone(self.page.evaluate(_FIT_JS, [PRINT_WIDTH_DOTS, 1]))
                self.assertEqual(self.page.evaluate(_OVERFLOW_JS), [])
                self.assertEqual(len(self.texts(".rp-task")), 35)
                self.assertEqual(self.texts(".rp-step-n")[-1], "27")

    def test_bad_data_is_refused(self):
        item = {"name": "sal"}
        step = {"verb": "Sirva"}
        for data, pattern in (
            ({"extra": 1}, r"^data\.extra: unknown field$"),
            ({"groups": [{"items": [{**item, "note": "x"}]}]}, r"^data\.groups\[0\]\.items\[0\]\.note: unknown field$"),
            ({"name": " "}, r"^data\.name: expected non-blank text$"),
            ({"groups": [{"name": "​", "items": [item]}]}, r"^data\.groups\[0\]\.name: expected non-blank text$"),
            ({"groups": [{"items": [{"name": ""}]}]}, r"^data\.groups\[0\]\.items\[0\]\.name: expected non-blank text$"),
            ({"phases": [{"steps": [{"verb": "  "}]}]}, r"^data\.phases\[0\]\.steps\[0\]\.verb: expected non-blank text$"),
            ({"name": "W" * 65}, r"^data\.name: expected at most 64 characters$"),
            ({"groups": [{"name": "W" * 49, "items": [item]}]}, r"^data\.groups\[0\]\.name: expected at most 48 characters$"),
            ({"groups": [{"items": [{"name": "W" * 91}]}]}, r"^data\.groups\[0\]\.items\[0\]\.name: expected at most 90 characters$"),
            ({"groups": [{"items": [{**item, "amount": "W" * 17}]}]}, r"^data\.groups\[0\]\.items\[0\]\.amount: expected at most 16 characters$"),
            ({"phases": [{"steps": [{**step, "text": "W" * 211}]}]}, r"^data\.phases\[0\]\.steps\[0\]\.text: expected at most 210 characters$"),
            ({"phases": [{"steps": [{"verb": "W" * 41}]}]}, r"^data\.phases\[0\]\.steps\[0\]\.verb: expected at most 40 characters$"),
            ({"phases": [{"steps": [{**step, "time": "W" * 29}]}]}, r"^data\.phases\[0\]\.steps\[0\]\.time: expected at most 28 characters$"),
            ({"groups": [{"items": [{**item, "kind": "garnish"}]}]}, r"^data\.groups\[0\]\.items\[0\]\.kind: expected one of optional, base$"),
            ({"portions": 0}, r"^data\.portions: expected a whole number from 1 to 99$"),
            ({"portions": 100}, r"^data\.portions: expected a whole number from 1 to 99$"),
            ({"groups": []}, r"^data\.groups: expected at least 1 item$"),
            ({"groups": [{"items": []}]}, r"^data\.groups\[0\]\.items: expected at least 1 item$"),
            ({"phases": [{"steps": []}]}, r"^data\.phases\[0\]\.steps: expected at least 1 item$"),
            ({"groups": [{"items": [item]}] * 7}, r"^data\.groups: expected at most 6 items$"),
            ({"phases": [{"steps": [step]}] * 9}, r"^data\.phases: expected at most 8 items$"),
            ({"groups": [{"items": [item] * 36}]}, r"^data\.groups\[0\]\.items: expected at most 35 items$"),
            ({"groups": [{"items": [item] * 6}] * 6}, r"^data\.groups: expected at most 35 items across all groups$"),
            ({"phases": [{"steps": [step] * 28}]}, r"^data\.phases\[0\]\.steps: expected at most 27 items$"),
            ({"phases": [{"steps": [step] * 4}] * 7}, r"^data\.phases: expected at most 27 steps across all phases$"),
        ):
            with self.subTest(data), self.assertRaisesRegex(TemplateError, pattern):
                render_template(self.page, recipe(**data))

    def test_wrong_schema_version_is_refused(self):
        with self.assertRaisesRegex(TemplateError, r'^template "recipe" expects schemaVersion 1, got 2$'):
            render_template(self.page, {**RECIPE, "schemaVersion": 2})


if __name__ == "__main__":
    unittest.main()
