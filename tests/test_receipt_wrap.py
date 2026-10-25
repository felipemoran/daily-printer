import json
import sys
import unittest
from pathlib import Path

from tests.web_build import build_web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SAMPLE = json.loads((ROOT / "samples" / "receipt-sample.json").read_text(encoding="utf-8"))
EMAIL = "wwwwwwwwwwwwwwwwww@mmmmmmmmmmmmmmmmm.com"
NO_WRAP = "#receipt, #receipt * { overflow-wrap: normal !important; }"

OVERFLOW = """() => {
  const receipt = document.querySelector('#receipt'), left = receipt.getBoundingClientRect().left;
  return [...receipt.querySelectorAll('*')]
    .filter((el) => el.scrollWidth > el.clientWidth || el.getBoundingClientRect().right - left > 384)
    .map((el) => el.outerHTML.slice(0, 80));
}"""

BOXES = """() => [...document.querySelectorAll('#receipt *')].map((el) => {
  const r = el.getBoundingClientRect();
  return [el.className, r.top, r.width, r.height];
})"""


def setUpModule():
    build_web()


class ReceiptWrapTest(unittest.TestCase):
    def render(self, payload, css=None):
        from playwright.sync_api import sync_playwright
        from raster_capture import static_server

        with static_server(ROOT / "web" / "dist") as port, sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 384, "height": 720})
            page.route("**/payload.json", lambda route: route.fulfill(json=payload))
            page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="networkidle")
            page.wait_for_selector("#receipt .receipt-header, #receipt .section-header")
            if css:
                page.add_style_tag(content=css)
            result = page.evaluate(OVERFLOW), page.evaluate(BOXES)
            browser.close()
        return result

    def test_long_unbroken_tokens_stay_inside_the_band(self):
        payload = {
            "schemaVersion": SAMPLE["schemaVersion"],
            "blocks": [
                {"type": "receipt_header", "date": EMAIL},
                {"type": "section_header", "title": EMAIL},
                {"type": "day_header", "title": EMAIL},
                {"type": "task", "content": EMAIL},
            ],
        }
        unwrapped = " ".join(self.render(payload, NO_WRAP)[0])
        for name in ("receipt-header__date", "section-header", "day-header", "task-content"):
            self.assertIn(f'class="{name}"', unwrapped, "this block no longer overflows without the fix")
        self.assertEqual(self.render(payload)[0], [])

    def test_normal_text_keeps_its_layout(self):
        payload = dict(SAMPLE, blocks=[*SAMPLE["blocks"], {"type": "day_header", "title": "Tue Apr 14"}])
        overflow, boxes = self.render(payload)
        self.assertEqual(overflow, [])
        self.assertEqual(boxes, self.render(payload, NO_WRAP)[1])


if __name__ == "__main__":
    unittest.main()
