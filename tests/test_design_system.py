import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import print_profile  # noqa: E402

_spec = importlib.util.spec_from_file_location("sync_design_system", ROOT / "src" / "scripts" / "sync_design_system.py")
sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync)


class GeneratedFilesTest(unittest.TestCase):
    def test_generated_web_files_match_the_mirror(self):
        self.assertEqual(sync.stale_files(), [], "run: uv run src/scripts/sync_design_system.py")

    def test_bundle_css_loads_no_web_fonts(self):
        self.assertNotIn("fonts.googleapis.com", sync.generated_files()["bundle.css"])


class TokensCssTest(unittest.TestCase):
    TOKENS = {
        "color": {"themes": [{"id": "paper"}], "tokens": [
            {"name": "ink", "value": "#000000"},
            {"name": "text", "value": "{ink}"},
            {"name": "rule", "value": {"paper": "#111111"}},
        ]},
        "spacing": {"tokens": [{"name": "space-1", "value": 4}]},
        "type": {
            "families": {"mono": '"IBM Plex Mono", monospace'},
            "groups": [{"name": "Mono", "family": "mono", "styles": [
                {"name": "body", "fontSize": "18px", "lineHeight": 1.25, "fontWeight": 500},
                {"name": "label", "fontSize": 16, "lineHeight": 24, "fontWeight": 700, "letterSpacing": "3px"},
            ]}],
        },
    }

    def test_variables_aliases_and_type_classes(self):
        css = sync.tokens_css(self.TOKENS)
        for expected in (
            "--ink: #000000;",
            "--text: var(--ink);",
            "--rule: #111111;",
            "--space-1: 4px;",
            '--font-mono: "IBM Plex Mono", monospace;',
            ".body { font-family: var(--font-mono); font-size: 18px; line-height: 1.25; font-weight: 500; }",
            ".label { font-family: var(--font-mono); font-size: 16px; line-height: 24px; font-weight: 700; letter-spacing: 3px; }",
        ):
            self.assertIn(expected, css)

    def test_refuses_a_second_theme(self):
        tokens = {"color": {"themes": [{"id": "light"}, {"id": "dark"}], "tokens": []}}
        with self.assertRaises(sync.SyncError):
            sync.tokens_css(tokens)

    def test_refuses_a_renamed_bundle(self):
        with self.assertRaises(sync.SyncError):
            sync.check_namespace('/* @ds-bundle: {"format":4,"namespace":"Other","components":[]} */')


@unittest.skipUnless((ROOT / "web" / "node_modules").is_dir(), "needs web dependencies: make setup-web")
class ThermalPagesTest(unittest.TestCase):
    """Pages built on the design system render through the print pipeline intact."""

    @classmethod
    def setUpClass(cls):
        subprocess.run(["npm", "run", "build"], cwd=ROOT / "web", check=True, capture_output=True)

    def test_ticket_template_renders_with_self_hosted_fonts_and_its_own_weights(self):
        from playwright.sync_api import sync_playwright
        from ticket_templates import ORIGIN, open_render_page
        payload = json.loads((ROOT / "samples" / "templates" / "ticket.json").read_text(encoding="utf-8"))
        requests = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = open_render_page(browser)
            page.on("request", lambda request: requests.append(request.url))
            page.reload(wait_until="load")
            page.evaluate("(payload) => window.renderTemplate(payload)", payload)
            page.evaluate(print_profile.capture_options(print_profile.DEFAULT_PROFILE)["prepare_js"])
            result = page.evaluate("""async () => {
              await document.fonts.ready;
              const receipt = document.querySelector('#receipt');
              return {
                width: receipt.getBoundingClientRect().width,
                displayWeight: getComputedStyle(receipt.querySelector('.display-xl')).fontWeight,
                // check() is true when no face matches at all, so read the faces' status.
                loaded: [...document.fonts].filter((face) => face.status === 'loaded')
                  .map((face) => `${face.family.replaceAll('"', '')} ${face.weight}`).sort(),
              };
            }""")
            browser.close()
        self.assertEqual((result["width"], result["displayWeight"]), (384, "900"))
        for face in ("Archivo 400 900", "IBM Plex Mono 500", "IBM Plex Mono 700"):
            self.assertIn(face, result["loaded"])
        self.assertIn(f"{ORIGIN}/render.html", requests)
        self.assertEqual([url for url in requests if not url.startswith(f"{ORIGIN}/")], [])

    def test_every_test_strip_renders_a_printable_receipt(self):
        from playwright.sync_api import sync_playwright
        from raster_capture import static_server
        strips = sorted(path.parent.name for path in (ROOT / "design-system" / "components").glob("Test*/preview.html"))
        self.assertTrue(strips)
        with static_server(ROOT / "web" / "dist") as port, sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 384, "height": 720})
            for name in strips:
                with self.subTest(name):
                    page.goto(f"http://127.0.0.1:{port}/preview.html?c={name}", wait_until="networkidle")
                    receipt = page.locator("#receipt")
                    self.assertEqual(receipt.bounding_box()["width"], 384)
                    self.assertIn("TEST ·", receipt.inner_text())
            browser.close()


if __name__ == "__main__":
    unittest.main()
