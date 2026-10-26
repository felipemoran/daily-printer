import copy
import json
import re
import subprocess
import sys
import unittest
from datetime import datetime
from pathlib import Path

from tests.web_build import build_web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ticket_templates import _FIT_JS, PRINT_WIDTH_DOTS, TemplateError, open_render_page, render_template  # noqa: E402

RECIPE = json.loads((ROOT / "samples" / "templates" / "recipe.json").read_text(encoding="utf-8"))
ONE_METRE = 8000
NOW = datetime(2026, 10, 26, 14, 8)
URL = "https://mise-en-place.felipemoran.com/#receita=madalena"


def uses(*pairs):
    return [{"name": name, "amount": amount} if amount else {"name": name} for amount, name in pairs]


# The longest print in the mise-en-place catalogue (2026-10, 60 recipes), with its 33 cook-mode references.
MADALENA = {"template": "recipe", "schemaVersion": 1, "data": {
    "name": "Torta madalena", "portions": 4, "url": URL,
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
            {"verb": "Cozinhe as batatas", "time": "20 min", "text": "Em pedaços médios, cobertas de água, com 1 colher (chá) de sal e o louro. Ferveu, fogo médio.",
             "uses": uses(("1 kg", "Batata (asterix ou monalisa)"), ("1 folha", "Folha de louro"), ("a gosto", "Sal"))},
            {"verb": "Reserve a água", "time": "2 min", "text": "Guarde 2 xícaras da água do cozimento para o recheio e escorra as batatas.",
             "uses": uses(("480 ml", "Água do cozimento"))},
            {"verb": "Aqueça o leite", "time": "1 min", "text": "No micro-ondas.", "uses": uses(("300 ml", "Leite"))},
            {"verb": "Esprema as batatas", "time": "3 min", "text": "Ainda quentes, sobre a panela seca.", "uses": uses(("1 kg", "Batata"))},
            {"verb": "Finalize o purê", "time": "5 min", "text": "Fogo médio, leite aos poucos com o batedor de arame, depois a manteiga. Fora do fogo, queijo e noz-moscada.",
             "uses": uses(("300 ml", "Leite"), ("28,5 g", "Manteiga"), ("19,8 g", "Parmesão em peça"), ("a gosto", "Noz-moscada"), ("a gosto", "Sal"))}]},
        {"name": "Recheio", "steps": [
            {"verb": "Preaqueça o forno", "time": "10 min", "text": "Unte com azeite um refratário de 30 × 20 cm.",
             "uses": uses(("200 °C", "Forno"), ("", "Azeite"))},
            {"verb": "Prepare os legumes", "time": "8 min", "text": "Cenoura no ralo fino, cebola e alho picados fino, tomilho debulhado.",
             "uses": uses(("150 g", "Cenoura"), ("1 un", "Cebola"), ("2 dentes", "Alho"), ("0,2 maço", "Tomilho"))},
            {"verb": "Doure a carne", "time": "10 min", "text": "1 colher (sopa) de azeite, uma pitada de sal e a farinha polvilhada, até a farinha dourar. Reserve.",
             "uses": uses(("500 g", "Carne moída (patinho)"), ("15 g", "Farinha de trigo"), ("15 ml", "Azeite"), ("a gosto", "Sal"))},
            {"verb": "Refogue os legumes", "time": "6 min", "text": "½ colher (sopa) de azeite: cebola até murchar, cenoura por 2 min, alho e anchova por 1 min.",
             "uses": uses(("1 un", "Cebola"), ("150 g", "Cenoura"), ("2 dentes", "Alho"), ("3 un", "Filé de anchova"))},
            {"verb": "Deglaceie", "time": "4 min", "text": "Extrato, depois a água das batatas, raspando o fundo. Shoyu, vinagre e cravo até ferver.",
             "uses": uses(("33 g", "Extrato de tomate"), ("15 ml", "Shoyu"), ("15 ml", "Vinagre de vinho"), ("a gosto", "Cravo em pó"))},
            {"verb": "Cozinhe o recheio", "time": "10 min", "text": "Carne de volta, ervilha e tomilho. Fogo baixo, mexendo de vez em quando, até encorpar.",
             "uses": uses(("500 g", "Carne moída (patinho)"), ("80,4 g", "Ervilha congelada"), ("0,2 maço", "Tomilho"))}]},
        {"name": "Montagem", "steps": [
            {"verb": "Monte a torta", "time": "5 min", "text": "Recheio no refratário, purê por cima com as costas da colher. Risque com o garfo e polvilhe queijo.",
             "uses": uses(("a gosto", "Parmesão em peça"))},
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
# Line boxes of each element's text: 1 means it did not wrap.
_LINES_JS = """(selector) => [...document.querySelectorAll('#receipt ' + selector)].map((el) => {
  const range = document.createRange();
  range.selectNodeContents(el);
  return new Set([...range.getClientRects()].map((rect) => rect.top)).size;
})"""
# Stroked and filled boxes whose edges must sit on whole dots.
_EDGES_JS = """() => [...document.querySelectorAll('#receipt [data-snap], #receipt canvas, #receipt .kr-tile, #receipt .kr-step, #receipt .kr-phase, #receipt .kr-group')]
  .map((el) => el.getBoundingClientRect()).map((r) => [r.left, r.right, r.top, r.bottom])"""
_USES_JS = """() => [...document.querySelectorAll('#receipt .kr-step')].map((step) =>
  [...step.querySelectorAll('.kr-use-name')].map((name) => [name.previousElementSibling.textContent, name.textContent]))"""
_LENGTH_REFUSAL = r"^the receipt would print [\d.]+ cm long; the limit is 100 cm$"


def setUpModule():
    build_web()


def glue(text):
    return re.sub(r"(\d[\d.,/]*|[½¼¾≈×])\s+", "\\1\u00a0", text)


def display(name):
    glued = glue(name)
    return glued[:1].upper() + glued[1:]


def qr_matrix(text):
    """qrMatrix in web/src/templates/qr.ts, from the same encoder."""
    script = ("import qrcode from 'qrcode-generator'; const code = qrcode(0, 'M'); code.addData(process.argv[1]); code.make();"
              "const n = code.getModuleCount(); console.log(JSON.stringify(Array.from({ length: n }, (_, r) =>"
              " Array.from({ length: n }, (_, c) => (code.isDark(r, c) ? '1' : '0')).join(''))))")
    result = subprocess.run(["node", "--input-type=module", "-e", script, text], cwd=ROOT / "web",
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def recipe(**data):
    payload = copy.deepcopy(RECIPE)
    payload["data"].update(data)
    for key in [key for key, value in data.items() if value is None]:
        del payload["data"][key]
    return payload


def maximal(glyph):
    """Every string at its cap and every list at its cap or total."""
    item = {"name": glyph * 90, "amount": glyph * 16, "kind": "base"}
    used = {"name": glyph * 90, "amount": glyph * 16}
    step = {"verb": glyph * 40, "time": glyph * 28, "text": glyph * 210}
    full = {**step, "uses": [used] * 10}
    return recipe(
        name=glyph * 64, portions=99, url="W" * 120,
        groups=[{"name": glyph * 48, "items": [item] * 6}] * 5 + [{"name": glyph * 48, "items": [item] * 5}],
        phases=[{"name": glyph * 28, "steps": [full] * 4}, {"name": glyph * 28, "steps": [full, step, step, step]}]
        + [{"name": glyph * 28, "steps": [step] * 4}] * 4 + [{"name": glyph * 28, "steps": [step] * 3}],
    )


class RecipeTest(unittest.TestCase):
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

    def assert_in_order(self, expected):
        text = self.page.evaluate("() => document.querySelector('#receipt').textContent")
        at = 0
        for part in expected:
            found = text.find(part, at)
            self.assertNotEqual(found, -1, f"{part!r} missing or out of order")
            at = found + len(part)

    def assert_whole_edges(self):
        edges = self.page.evaluate(_EDGES_JS)
        self.assertTrue(edges)
        for edge in edges:
            self.assertTrue(all(float(value).is_integer() for value in edge), edge)

    def test_every_ingredient_and_amount_prints_in_the_order_sent(self):
        # A dropped list element still renders a print that looks complete.
        self.render(RECIPE)
        items = [item for group in RECIPE["data"]["groups"] for item in group["items"]]
        self.assertEqual(self.texts(".kr-amount"), [item.get("amount", "") for item in items])
        self.assertEqual(self.page.evaluate(_TEXTS_JS, ".kr-ingredient"),
                         [display(item["name"]) + {"optional": "OPCIONAL", "base": "RECEITA BASE"}.get(item.get("kind"), "") for item in items])

    def test_names_print_capitalized_with_numbers_glued_to_their_unit(self):
        self.render(recipe(groups=[{"items": [{"name": "massa de 2 ovos", "amount": "1 un"}, {"name": "½ maço de salsinha"}]}],
                           phases=[{"steps": [{"verb": "Sirva", "text": "em 2 pratos", "uses": [{"name": "água de 3 × lata"}]}]}]))
        self.assertEqual(self.texts(".kr-ingredient"), ["Massa de 2\u00a0ovos", "½\u00a0maço de salsinha"])
        self.assertEqual(self.texts(".kr-use-name"), ["Água de 3\u00a0×\u00a0lata"])
        self.assertIn("em 2\u00a0pratos", self.texts(".kr-step-text")[0])

    def test_steps_number_continuously_across_phases(self):
        self.render(RECIPE)
        steps = [step for phase in RECIPE["data"]["phases"] for step in phase["steps"]]
        self.assertEqual(self.texts(".kr-step-n"), [f"{n:02}" for n in range(1, len(steps) + 1)])
        self.assertEqual(self.texts(".kr-verb"), [step["verb"] for step in steps])
        self.assert_in_order([part for step in steps for part in (step["verb"], step.get("time", ""), glue(step.get("text", "")))])

    def test_phase_heads_show_their_step_range(self):
        self.render(RECIPE)
        self.assertEqual(self.texts(".kr-phase-name"), [phase["name"] for phase in RECIPE["data"]["phases"]])
        self.assertEqual(self.texts(".kr-range"), ["passos 1–2", "passos 3–7", "passos 8–9", "passos 10–12"])
        self.render(recipe(phases=[{"name": "Antes", "steps": [{"verb": "Lave"}]}, {"steps": [{"verb": "Corte"}, {"verb": "Sirva"}]}]))
        self.assertEqual(self.texts(".kr-range"), ["passo 1", "passos 2–3"])

    def test_unnamed_phase_keeps_its_rule_and_range(self):
        self.render(recipe(phases=[{"steps": [{"verb": "Sirva"}]}]))
        self.assertEqual(self.texts(".kr-phase-name"), [""])
        self.assertEqual(self.texts(".kr-range"), ["passo 1"])

    def test_kind_tags_mark_exactly_those_items(self):
        self.render(RECIPE)
        items = [item for group in RECIPE["data"]["groups"] for item in group["items"]]
        tags = self.page.evaluate("() => [...document.querySelectorAll('#receipt .kr-ingredient')].map((el) => el.querySelector('.kr-kind')?.textContent ?? null)")
        self.assertEqual(tags, [{"optional": "OPCIONAL", "base": "RECEITA BASE"}.get(item.get("kind")) for item in items])
        self.assertEqual(sorted(set(tags) - {None}), ["OPCIONAL", "RECEITA BASE"])

    def test_named_groups_print_heads(self):
        self.render(RECIPE)
        self.assertEqual(self.texts(".kr-group-name"), [group["name"] for group in RECIPE["data"]["groups"]])

    def test_one_unnamed_group_prints_its_rule_only(self):
        self.render(recipe(groups=[{"items": [{"name": "arroz", "amount": "200 g"}, {"name": "sal", "amount": "a gosto"}]}], phases=None))
        self.assertEqual(self.texts(".kr-group-name"), [])
        self.assertEqual(len(self.texts(".kr-group")), 1)
        self.assertEqual(self.texts(".kr-ingredient"), ["Arroz", "Sal"])

    def test_tiles_count_portions_items_and_steps(self):
        self.render(RECIPE)
        items = sum(len(group["items"]) for group in RECIPE["data"]["groups"])
        steps = sum(len(phase["steps"]) for phase in RECIPE["data"]["phases"])
        self.assertEqual(self.texts(".kr-tile"), [f"PORÇÕES{RECIPE['data']['portions']}", f"INGREDIENTES{items}", f"PASSOS{steps}"])

    def test_steps_section_and_tile_are_omitted_without_phases(self):
        for phases in (None, []):
            with self.subTest(phases=phases):
                self.render(recipe(phases=phases))
                self.assertNotIn("PASSOS", self.texts(".rp-label"))
                self.assertEqual(self.texts(".kr-step"), [])
                self.assertEqual(len(self.texts(".kr-tile")), 2)

    def test_item_without_amount_leaves_its_amount_cell_empty(self):
        self.render(recipe(groups=[{"items": [{"name": "salsinha picada"}, {"name": "sal", "amount": "a gosto"}]}]))
        self.assertEqual(self.texts(".kr-amount"), ["", "a gosto"])
        self.assertEqual(self.texts(".kr-ingredient"), ["Salsinha picada", "Sal"])

    def test_step_without_text_time_or_uses_prints_its_verb(self):
        self.render(recipe(phases=[{"steps": [{"verb": "Sirva"}]}]))
        self.assertEqual(self.texts(".kr-step-text"), ["Sirva"])
        self.assertEqual(self.texts(".kr-time"), [])
        self.assertEqual(self.texts(".kr-uses"), [])

    def test_uses_print_in_order_under_their_step(self):
        self.render(RECIPE)
        steps = [step for phase in RECIPE["data"]["phases"] for step in phase["steps"]]
        self.assertTrue(any(step.get("uses") for step in steps))
        self.assertEqual(self.page.evaluate(_USES_JS),
                         [[[used.get("amount", ""), display(used["name"])] for used in step.get("uses", [])] for step in steps])

    def test_amounts_times_and_ranges_never_wrap(self):
        # A long name beside "200 ml" once pushed "ml" onto a line of its own.
        long = "creme de leite fresco com teor de gordura acima de trinta e cinco por cento, gelado"
        self.render(recipe(
            groups=[{"items": [{"name": long, "amount": "200 ml"}, {"name": long, "amount": "1,25 kg (aprox.)"}]}],
            phases=[{"name": "Molho", "steps": [
                {"verb": "Deixe descansar tampado", "time": "até ferver, cerca de 10 min", "text": long, "uses": [{"name": long, "amount": "200 ml"}]},
            ] * 12}],
        ))
        for selector in (".kr-amount", ".kr-use-amount", ".kr-time", ".kr-range", ".kr-foot-portions"):
            with self.subTest(selector):
                lines = self.page.evaluate(_LINES_JS, selector)
                self.assertTrue(lines)
                self.assertEqual(set(lines), {1})

    def test_portions_are_singular_for_one(self):
        for portions, tile, foot in ((1, "PORÇÃO1", "1 PORÇÃO"), (4, "PORÇÕES4", "4 PORÇÕES"), (99, "PORÇÕES99", "99 PORÇÕES")):
            with self.subTest(portions):
                self.render(recipe(portions=portions))
                self.assertEqual(self.texts(".kr-tile")[0], tile)
                self.assertEqual(self.texts(".kr-foot-portions"), [foot])

    def test_title_size_follows_name_length(self):
        for name, size in (("W" * 18, "92px"), ("W" * 19, "68px"), ("W" * 36, "68px"), ("W" * 37, "50px")):
            with self.subTest(len(name)):
                self.render(recipe(name=name))
                self.assertEqual(self.page.evaluate("() => getComputedStyle(document.querySelector('#receipt .kr-title')).fontSize"), size)

    def test_qr_encodes_the_url_on_whole_modules(self):
        self.render(MADALENA)
        canvas = self.page.evaluate("""() => {
          const canvas = document.querySelector('#receipt canvas'), rect = canvas.getBoundingClientRect();
          const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
          const n = canvas.width / 5;
          const rows = Array.from({ length: n }, (_, y) => Array.from({ length: n }, (_, x) =>
            pixels[((y * 5 + 2) * canvas.width + x * 5 + 2) * 4] < 128 ? '1' : '0').join(''));
          return { rows, rect: [rect.left, rect.top, rect.width, rect.height], size: [canvas.width, canvas.height] };
        }""")
        matrix = qr_matrix(URL)
        self.assertEqual(canvas["rows"], matrix)
        self.assertEqual(canvas["size"], [len(matrix) * 5] * 2)
        self.assertEqual(canvas["rect"][2:], canvas["size"])
        self.assertTrue(all(float(value).is_integer() for value in canvas["rect"]), canvas["rect"])
        self.assertEqual(self.texts(".kr-url"), ["mise-en-place.felipemoran.com/#receita=madalena"])

    def test_footer_prints_the_render_time(self):
        self.render(RECIPE)
        self.assertEqual(self.texts(".kr-printed"), ["impresso em 26 out 2026 · 14:08"])
        try:
            self.page.clock.set_fixed_time(datetime(2027, 1, 5, 9, 3))
            self.render(RECIPE)
            self.assertEqual(self.texts(".kr-printed"), ["impresso em 5 jan 2027 · 09:03"])
        finally:
            self.page.clock.set_fixed_time(NOW)

    def test_tags_tiles_rules_and_qr_sit_on_whole_pixels(self):
        # A fractional edge smears a 2px stroke over three dot columns.
        for payload in (RECIPE, MADALENA, maximal("W"), maximal("漢")):
            with self.subTest(payload["data"]["name"][:8]):
                try:
                    render_template(self.page, payload, max_height_dots=ONE_METRE)
                except TemplateError as error:
                    self.assertRegex(str(error), _LENGTH_REFUSAL)
                self.assert_whole_edges()

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
                self.assertEqual(len(self.texts(".kr-ingredient")), 35)
                self.assertEqual(self.texts(".kr-step-n")[-1], "27")
                self.assertEqual(len(self.texts(".kr-use-name")), 50)

    def test_bad_data_is_refused(self):
        item = {"name": "sal"}
        step = {"verb": "Sirva"}
        used = {"name": "sal"}
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
            ({"url": None}, r"^data\.url: expected string$"),
            ({"url": "https://x.io/" + "a" * 108}, r"^data\.url: expected at most 120 characters$"),
            ({"url": "https://x.io/#receita=pão"}, r"^data\.url: expected ASCII \(percent-encode the URL\)$"),
            ({"phases": [{"steps": [{**step, "uses": [{**used, "unit": "g"}]}]}]}, r"^data\.phases\[0\]\.steps\[0\]\.uses\[0\]\.unit: unknown field$"),
            ({"phases": [{"steps": [{**step, "uses": [{"name": " "}]}]}]}, r"^data\.phases\[0\]\.steps\[0\]\.uses\[0\]\.name: expected non-blank text$"),
            ({"phases": [{"steps": [{**step, "uses": [{"name": "W" * 91}]}]}]}, r"^data\.phases\[0\]\.steps\[0\]\.uses\[0\]\.name: expected at most 90 characters$"),
            ({"phases": [{"steps": [{**step, "uses": [{**used, "amount": "W" * 17}]}]}]}, r"^data\.phases\[0\]\.steps\[0\]\.uses\[0\]\.amount: expected at most 16 characters$"),
            ({"phases": [{"steps": [{**step, "uses": [used] * 11}]}]}, r"^data\.phases\[0\]\.steps\[0\]\.uses: expected at most 10 items$"),
            ({"phases": [{"steps": [{**step, "uses": [used] * 10}] * 5 + [{**step, "uses": [used]}]}]}, r"^data\.phases: expected at most 50 uses across all steps$"),
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
