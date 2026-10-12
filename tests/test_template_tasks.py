import sys
import unittest
from datetime import date, datetime
from pathlib import Path

from tests.web_build import build_web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from todoist_api_python.models import Due, Task  # noqa: E402

from tasks_template import META_MAX, TASKS_MAX, TITLE_MAX, tasks_payload  # noqa: E402
from todoist_client import TaskSections  # noqa: E402

NOW = datetime(2026, 10, 12, 7, 30).astimezone()
URL = "https://example.com/" + "a" * 200


def task(content, due=None, priority=1, labels=None):
    return Task(
        id="1", content=content, description="", project_id="p", section_id=None, parent_id=None,
        labels=labels, priority=priority, due=Due(date=due, string="") if due else None, deadline=None,
        duration=None, is_collapsed=False, order=1, assignee_id=None, assigner_id=None, completed_at=None,
        creator_id="u", created_at=NOW, updated_at=NOW,
    )


SECTIONS = TaskSections(
    today=[
        task("Review Q4 roadmap draft", datetime(2026, 10, 12, 14, 30).astimezone(), 4, ["planning"]),
        task("Read [the spec](https://example.com/spec)", date(2026, 10, 12), 3),
        task("Book flights for offsite"),
    ],
    overdue=[
        task("Send invoice", date(2026, 10, 9), 1, ["finance"]),
        task("Water plants", datetime(2026, 10, 11, 18, 0).astimezone()),
    ],
    upcoming=[task("Dentist", date(2026, 10, 13))],
)


class MappingTest(unittest.TestCase):
    def test_maps_today_and_overdue(self):
        self.assertEqual(tasks_payload(SECTIONS, NOW), {
            "template": "tasks",
            "schemaVersion": 1,
            "data": {
                "weekday": "MON",
                "date": "12 OCT",
                "year": "2026",
                "tasks": [
                    {"title": "Review Q4 roadmap draft", "meta": "14:30 · planning", "priority": "P1"},
                    {"title": "Read the spec", "priority": "P2"},
                    {"title": "Book flights for offsite"},
                    {"title": "Send invoice", "meta": "OVERDUE 3D · finance"},
                    {"title": "Water plants", "meta": "OVERDUE 1D"},
                ],
                "printedAt": "07:30",
            },
        })

    def test_no_tasks(self):
        self.assertEqual(tasks_payload(TaskSections(), NOW)["data"]["tasks"], [])

    def test_clips_by_code_points(self):
        # The template counts code points: an emoji is one, though it takes two UTF-16 units.
        row = tasks_payload(TaskSections(today=[task("🔥" * 200, labels=["🏷️" * 50])]), NOW)["data"]["tasks"][0]
        self.assertEqual(row["title"], "🔥" * (TITLE_MAX - 1) + "…")
        self.assertEqual(len(row["meta"]), META_MAX)
        self.assertTrue(row["meta"].endswith("…"))
        exact = tasks_payload(TaskSections(today=[task("🔥" * TITLE_MAX)]), NOW)["data"]["tasks"][0]
        self.assertEqual(exact["title"], "🔥" * TITLE_MAX)

    def test_caps_tasks_and_counts_the_rest(self):
        data = tasks_payload(TaskSections(today=[task(f"t{n}") for n in range(TASKS_MAX + 1)]), NOW)["data"]
        self.assertEqual(len(data["tasks"]), TASKS_MAX)
        self.assertEqual(data["more"], 1)


class RenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_web()
        from playwright.sync_api import sync_playwright

        from ticket_templates import open_render_page

        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)
        cls.page = open_render_page(cls.browser)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def render(self, payload):
        from ticket_templates import render_template

        return render_template(self.page, payload)

    def test_mapped_payload_renders(self):
        bitmap = self.render(tasks_payload(SECTIONS, NOW))
        self.assertEqual(bitmap.width, 384)
        self.assertTrue(0 < bitmap.histogram()[0] < bitmap.width * bitmap.height)

    def test_more_counts_in_open(self):
        payload = tasks_payload(TaskSections(today=[task(f"t{n}") for n in range(TASKS_MAX + 2)]), NOW)
        payload["data"]["tasks"] = payload["data"]["tasks"][:3]
        self.render(payload)
        text = self.page.inner_text("#receipt")
        self.assertIn("+2 MORE IN TODOIST", text)
        self.assertIn("5\nOPEN", text)

    def test_unbroken_text_stays_on_the_paper(self):
        row = {"title": URL[:TITLE_MAX], "meta": URL[:META_MAX], "priority": "P1"}
        payload = tasks_payload(TaskSections(), NOW)
        payload["data"]["tasks"] = [row]
        self.render(payload)
        overflow = self.page.evaluate("""() => [...document.querySelectorAll('#receipt *')]
            .filter((el) => el.scrollWidth > el.clientWidth || el.getBoundingClientRect().right > 384)
            .map((el) => el.className || el.tagName)""")
        self.assertEqual(overflow, [])


if __name__ == "__main__":
    unittest.main()
