import contextlib
import copy
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ticket_templates import TemplateError, open_render_page, render_template, template_names  # noqa: E402

SAMPLES = sorted((ROOT / "samples" / "templates").glob("*.json"))
TICKET = json.loads((ROOT / "samples" / "templates" / "ticket.json").read_text(encoding="utf-8"))
HAS_WEB = (ROOT / "web" / "node_modules").is_dir()


def setUpModule():
    if HAS_WEB:
        subprocess.run(["npm", "run", "build"], cwd=ROOT / "web", check=True, capture_output=True)


def ticket(**data):
    payload = copy.deepcopy(TICKET)
    payload["data"].update(data)
    return payload


class EnvelopeTest(unittest.TestCase):
    """Python refuses a malformed envelope before it reaches the page."""

    def test_wrong_types(self):
        for payload, field in (
            ([], "payload"),
            ({"template": 1, "schemaVersion": 1, "data": {}}, "template"),
            ({"template": "ticket", "schemaVersion": True, "data": {}}, "schemaVersion"),
            ({"template": "ticket", "schemaVersion": 1, "data": []}, "data"),
        ):
            with self.subTest(field), self.assertRaisesRegex(TemplateError, f"^{field}: expected"):
                render_template(None, payload)


@unittest.skipUnless(HAS_WEB, "needs web dependencies: make setup-web")
class RenderTest(unittest.TestCase):
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

    def assert_template_error(self, payload, pattern, **kwargs):
        start = time.monotonic()
        with self.assertRaisesRegex(TemplateError, pattern):
            render_template(self.page, payload, **kwargs)
        self.assertLess(time.monotonic() - start, 5)

    def test_sample_is_a_printable_bitmap(self):
        image = render_template(self.page, TICKET)
        self.assertEqual((image.mode, image.width), ("1", 384))
        self.assertIsNotNone(image.convert("L").point(lambda value: 255 - value).getbbox(), "blank render")

    def test_every_sample_renders(self):
        self.assertTrue(SAMPLES)
        for path in SAMPLES:
            with self.subTest(path.name):
                image = render_template(self.page, json.loads(path.read_text(encoding="utf-8")))
                self.assertEqual((image.mode, image.width), ("1", 384))

    def test_template_names_come_from_the_build(self):
        self.assertIn("ticket", template_names())

    def test_reused_page_renders_like_a_fresh_one(self):
        fresh_page = open_render_page(self.browser)
        try:
            fresh = render_template(fresh_page, TICKET).tobytes()
        finally:
            fresh_page.close()
        render_template(self.page, ticket(title="A much longer title " * 4, comment=None, fields=None))
        self.assertEqual(render_template(self.page, TICKET).tobytes(), fresh, "after another render")
        self.assert_template_error(ticket(id=1), "data.id: expected string")
        self.assertEqual(render_template(self.page, TICKET).tobytes(), fresh, "after invalid data")
        with self.failing_transition():
            self.assert_template_error(TICKET, "failed to render")
        self.assertEqual(render_template(self.page, TICKET).tobytes(), fresh, "after a render that threw")

    def test_unknown_template(self):
        self.assert_template_error({"template": "nope", "schemaVersion": 1, "data": {}}, 'unknown template "nope"; known: .*ticket')

    def test_wrong_schema_version(self):
        self.assert_template_error({**TICKET, "schemaVersion": 99}, "expects schemaVersion 1, got 99")

    def test_invalid_data_names_the_field_path(self):
        self.assert_template_error(ticket(fields=[{"label": "a", "value": "b"}, {"label": "c", "value": 3}]),
                                   r"^data\.fields\[1\]\.value: expected string$")
        self.assert_template_error(ticket(titel="typo"), r"^data\.titel: unknown field$")

    def test_component_that_throws_is_caught_by_the_error_boundary(self):
        with self.failing_transition():
            self.assert_template_error(TICKET, '^template "ticket" failed to render: boom$')

    def test_too_tall_fails_before_the_screenshot(self):
        with mock.patch.object(self.page, "locator", side_effect=AssertionError("screenshot taken")):
            self.assert_template_error(TICKET, "dots long; the limit is 100", max_height_dots=100)

    def test_landscape_render_is_rotated_onto_the_paper(self):
        page = open_render_page(self.browser)
        try:
            # No landscape template yet: mark the ticket landscape after it renders.
            page.evaluate("""() => {
              const render = window.renderTemplate;
              window.renderTemplate = async (payload) => {
                await render(payload);
                const receipt = document.querySelector('#receipt');
                receipt.dataset.orientation = 'landscape';
                receipt.style.width = '600px';
              };
            }""")
            image = render_template(page, TICKET)
        finally:
            page.close()
        self.assertEqual((image.mode, image.size), ("1", (384, 600)))

    @contextlib.contextmanager
    def failing_transition(self):
        transition = self.page.evaluate_handle("() => window.Thermal.Transition")
        self.page.evaluate("() => { window.Thermal.Transition = () => { throw new Error('boom'); }; }")
        try:
            yield
        finally:
            self.page.evaluate("(original) => { window.Thermal.Transition = original; }", transition)


@unittest.skipUnless(HAS_WEB, "needs web dependencies: make setup-web")
class CliTest(unittest.TestCase):
    """print_template.py reports sender errors as one line, without a traceback."""

    def run_cli(self, payload, artifact_dir):
        path = Path(artifact_dir) / "payload.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(ROOT / "src" / "scripts" / "print_template.py"), str(path),
             "--no-print", "--no-build", "--artifact-dir", artifact_dir],
            capture_output=True, text=True, check=False,
        )

    def test_sample_writes_a_png(self):
        with tempfile.TemporaryDirectory() as artifact_dir:
            result = self.run_cli(TICKET, artifact_dir)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((Path(artifact_dir) / "ticket.png").is_file())

    def test_template_error_is_one_line(self):
        with tempfile.TemporaryDirectory() as artifact_dir:
            result = self.run_cli({"template": "nope", "schemaVersion": 1, "data": {}}, artifact_dir)
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stderr, r'^ERROR: unknown template "nope"; known: .*\n$')


if __name__ == "__main__":
    unittest.main()
