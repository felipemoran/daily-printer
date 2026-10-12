import copy
import json
import sys
import unittest
from pathlib import Path

from tests.web_build import build_web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ticket_templates import TemplateError, open_render_page, render_template  # noqa: E402

SAMPLES = ROOT / "samples" / "templates"
INCIDENT = json.loads((SAMPLES / "incident.json").read_text(encoding="utf-8"))

# Every field at its limit, in the widest glyph.
WIDEST = {
    "severity": "WW", "id": "W" * 24, "openedAt": "W" * 8, "service": "W" * 40, "summary": "W" * 80,
    "log": [{"time": "W" * 6, "text": "W" * 80}] * 8, "ackBy": "W" * 5,
}

OVERFLOW_JS = """() => {
  const receipt = document.querySelector('#receipt');
  const right = receipt.getBoundingClientRect().left + 384;
  return [...receipt.querySelectorAll('*')]
    .filter((el) => el.scrollWidth > el.clientWidth || el.getBoundingClientRect().right > right)
    .map((el) => `${el.className || el.tagName}: ${el.textContent.slice(0, 20)}`);
}"""


def setUpModule():
    build_web()


def with_data(sample, **data):
    payload = copy.deepcopy(sample)
    payload["data"].update(data)
    return payload


class IncidentTest(unittest.TestCase):
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

    def test_blank_required_text_is_refused(self):
        for sample, field, value in ((INCIDENT, "severity", ""), (INCIDENT, "id", "#"), (INCIDENT, "ackBy", "  ")):
            with self.subTest(template=sample["template"], field=field), \
                    self.assertRaisesRegex(TemplateError, rf"^data\.{field}: expected non-blank text$"):
                render_template(self.page, with_data(sample, **{field: value}))
        with self.assertRaisesRegex(TemplateError, r"^data\.log\[0\]\.text: expected non-blank text$"):
            render_template(self.page, with_data(INCIDENT, log=[{"time": "13:52", "text": ""}]))

    def test_sender_hash_is_not_doubled(self):
        bare = render_template(self.page, INCIDENT).tobytes()
        hashed = render_template(self.page, with_data(INCIDENT, id="#INC-0937"))
        self.assertIn("#INC-0937", self.page.inner_text("#receipt"))
        self.assertNotIn("##", self.page.inner_text("#receipt"))
        self.assertEqual(hashed.tobytes(), bare)

    def test_longest_data_stays_inside_the_paper(self):
        image = render_template(self.page, with_data(INCIDENT, **WIDEST))
        self.assertEqual(self.page.evaluate(OVERFLOW_JS), [])
        self.assertEqual(image.width, 384)


if __name__ == "__main__":
    unittest.main()
