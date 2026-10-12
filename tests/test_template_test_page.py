import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ticket_templates import TemplateError, open_render_page, render_template  # noqa: E402

SAMPLE = json.loads((ROOT / "samples" / "templates" / "test-page.json").read_text(encoding="utf-8"))
HAS_WEB = (ROOT / "web" / "node_modules").is_dir()


def test_page(**data):
    return {"template": "test-page", "schemaVersion": 1, "data": data}


def setUpModule():
    if HAS_WEB:
        subprocess.run(["npm", "run", "build"], cwd=ROOT / "web", check=True, capture_output=True)


@unittest.skipUnless(HAS_WEB, "needs web dependencies: make setup-web")
class TestPageTest(unittest.TestCase):
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

    def test_empty_data_renders_well_under_the_length_limit(self):
        self.assertEqual(SAMPLE["data"], {})
        image = render_template(self.page, SAMPLE)
        self.assertEqual(image.width, 384)
        self.assertLess(image.height, 2000)
        self.assertIn("TEST PAGE", self.page.inner_text("#receipt"))

    def test_prints_the_sender_fields(self):
        render_template(self.page, test_page(printer="W" * 24, printedAt="W" * 16))
        self.assertEqual(self.lines()[2:4], ["W" * 24, "W" * 16])
        render_template(self.page, test_page(printedAt="06:00"))
        self.assertEqual(self.lines()[2], "06:00")
        render_template(self.page, SAMPLE)
        self.assertEqual(self.lines()[2], "LINE WEIGHT")

    def lines(self):
        return [line for line in self.page.inner_text("#receipt").splitlines() if line.strip()]

    def test_refuses_bad_data(self):
        cases = (
            (test_page(printer=" "), r"^data\.printer: expected non-blank text$"),
            (test_page(printer="W" * 25), r"^data\.printer: expected at most 24 characters$"),
            (test_page(printedAt=""), r"^data\.printedAt: expected non-blank text$"),
            (test_page(printedAt="W" * 17), r"^data\.printedAt: expected at most 16 characters$"),
            (test_page(printer=7), r"^data\.printer: expected string$"),
            (test_page(name="x"), r"^data\.name: unknown field$"),
        )
        for payload, pattern in cases:
            with self.subTest(pattern), self.assertRaisesRegex(TemplateError, pattern):
                render_template(self.page, payload)


if __name__ == "__main__":
    unittest.main()
