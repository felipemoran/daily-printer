import subprocess
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tasks_template import TITLE_MAX, tasks_payload  # noqa: E402

HAS_WEB = (ROOT / "web" / "node_modules").is_dir()
NOW = datetime(2026, 10, 12, 7, 30)

# The shape gather() returns: web/src/receiptPayload.ts, schemaVersion 2.
RECEIPT = {
    "schemaVersion": 2,
    "generatedAt": "2026-10-12T05:30:00Z",
    "blocks": [
        {"type": "receipt_header", "date": "Monday, Oct 12"},
        {"type": "section_header", "title": "TODAY — Mon Oct 12"},
        {"type": "task", "content": "Review Q4 roadmap draft", "time": "2:30 PM", "labels": ["planning"]},
        {"type": "task", "content": "Stand-up", "time": "9 AM"},
        {"type": "task", "content": "Book flights for offsite"},
        {"type": "section_header", "title": "OVERDUE", "count": 2},
        {"type": "task", "content": "Send invoice", "time": "Oct 9", "relative": "3 days ago", "labels": ["finance"]},
        {"type": "task", "content": "Water plants", "time": "Oct 11", "relative": "yesterday"},
        {"type": "section_header", "title": "UPCOMING"},
        {"type": "day_header", "title": "Tue Oct 13"},
        {"type": "task", "content": "Dentist", "time": "10 AM", "relative": "tomorrow"},
        {"type": "receipt_footer", "text": "abc · def"},
    ],
}


class MappingTest(unittest.TestCase):
    def test_maps_today_and_overdue(self):
        payload = tasks_payload(RECEIPT, NOW)
        self.assertEqual(payload["template"], "tasks")
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(payload["data"], {
            "weekday": "MON",
            "date": "12 OCT",
            "year": "2026",
            "tasks": [
                {"title": "Review Q4 roadmap draft", "meta": "14:30 · planning"},
                {"title": "Stand-up", "meta": "09:00"},
                {"title": "Book flights for offsite"},
                {"title": "Send invoice", "meta": "overdue · 3 days ago · finance"},
                {"title": "Water plants", "meta": "overdue · yesterday"},
            ],
            "printedAt": "07:30",
        })

    def test_no_tasks(self):
        payload = tasks_payload({"schemaVersion": 2, "blocks": []}, NOW)
        self.assertEqual(payload["data"]["tasks"], [])

    def test_long_title_is_clipped(self):
        receipt = {"blocks": [{"type": "section_header", "title": "TODAY — Mon Oct 12"},
                              {"type": "task", "content": "x" * 500}]}
        title = tasks_payload(receipt, NOW)["data"]["tasks"][0]["title"]
        self.assertEqual(len(title), TITLE_MAX)
        self.assertTrue(title.endswith("…"))


@unittest.skipUnless(HAS_WEB, "needs web dependencies: make setup-web")
class RenderTest(unittest.TestCase):
    """The mapped payload passes the template's parse and renders."""

    def test_mapped_payload_renders(self):
        from playwright.sync_api import sync_playwright

        from ticket_templates import open_render_page, render_template

        subprocess.run(["npm", "run", "build"], cwd=ROOT / "web", check=True, capture_output=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                bitmap = render_template(open_render_page(browser), tasks_payload(RECEIPT, NOW))
            finally:
                browser.close()
        self.assertEqual(bitmap.width, 384)
        self.assertGreater(bitmap.height, 500)
        self.assertLess(bitmap.histogram()[0], bitmap.width * bitmap.height)
        self.assertGreater(bitmap.histogram()[0], 0)


if __name__ == "__main__":
    unittest.main()
