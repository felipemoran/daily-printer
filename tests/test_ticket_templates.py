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

from tests.web_build import build_web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ticket_templates import (  # noqa: E402
    MAX_DEPTH, TemplateError, check_envelope, launch_browser, open_render_page, render_template, render_text,
    template_names,
)

SAMPLES = sorted((ROOT / "samples" / "templates").glob("*.json"))
TICKET = json.loads((ROOT / "samples" / "templates" / "ticket.json").read_text(encoding="utf-8"))
EFFECT_THROWS = "() => { window.React.useEffect(() => { throw new Error('effect boom'); }); return null; }"
NEVER_SETTLES = "() => { throw new Promise(() => {}); }"
SERVER_FAULT = "() => { throw Object.assign(new Error('database down'), { name: 'ServerFault' }); }"
GROW = "() => document.querySelector('#receipt').append(Object.assign(document.createElement('div'), { style: 'height: 48px' }))"
BOX = "() => window.React.createElement('div', %s)"
KEEPS_GROWING = """() => {
  const [height, setHeight] = window.React.useState(10);
  window.React.useEffect(() => {
    const timer = setTimeout(() => setHeight(height + 1));
    return () => clearTimeout(timer);
  }, [height]);
  return window.React.createElement('div', { style: { height } });
}"""


def ticket(**data):
    payload = copy.deepcopy(TICKET)
    payload["data"].update(data)
    return payload


SHORT_TICKET = ticket(fields=None, comment=None, qr=None)


def nested(levels, wrap=lambda value: [value]):
    """``ticket()`` with ``data.deep`` grown until the payload nests ``levels`` deep."""
    value = wrap(None)
    for _ in range(levels - 3):
        value = wrap(value)
    return ticket(deep=value)


def widest_ticket(glyph):
    """Every list at its cap and every string at its limit."""
    return ticket(
        kind=glyph * 16, time=glyph * 8, id=glyph * 16, title=glyph * 120,
        status={"from": glyph * 24, "to": glyph * 24},
        fields=[{"label": glyph * 16, "value": glyph * 32}] * 10,
        comment={"text": glyph * 280, "author": glyph * 32},
        qr={"text": "W" * 120, "lines": [glyph * 40] * 3},
    )


# No web/dist needed: the template list is the only thing check_envelope reads from the build.
@mock.patch("ticket_templates.template_names", lambda: ["ticket"])
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

    def test_payload_size_is_capped(self):
        with self.assertRaisesRegex(TemplateError, "^payload: .* bytes; the limit is 65536$"):
            render_template(None, ticket(title="x" * 70_000))

    def test_payload_size_counts_utf8_bytes(self):
        # 50 KB as UTF-8; escaped to ASCII it would be 130 KB.
        check_envelope(ticket(title="\u00e7\u00e3o" * 10_000))
        with self.assertRaisesRegex(TemplateError, r"^payload: \d+ bytes; the limit is 65536$"):
            check_envelope(ticket(title="\u00e7\u00e3o" * 14_000))

    def test_deep_payload_is_a_sender_fault(self):
        calls = {"check_envelope": check_envelope, "render_template": lambda payload: render_template(None, payload),
                 "render_text": lambda payload: render_text(None, payload)}
        # 50,000 levels: json.dumps raises RecursionError. 150: page.evaluate hangs.
        for shape, wrap in (("list", lambda value: [value]), ("dict", lambda value: {"key": value})):
            for levels in (50_000, 150, MAX_DEPTH + 1):
                payload = nested(levels, wrap)
                for name, call in calls.items():
                    with self.subTest(shape=shape, levels=levels, call=name), \
                            self.assertRaisesRegex(TemplateError, f"^payload: nested more than {MAX_DEPTH} levels deep$"):
                        call(payload)
            check_envelope(nested(MAX_DEPTH, wrap))

    def test_unknown_template_fails_without_a_page(self):
        with self.assertRaisesRegex(TemplateError, '^unknown template "nope"; known: .*ticket'):
            render_template(None, {"template": "nope", "schemaVersion": 1, "data": {}})


class RenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_web()
        from playwright.sync_api import sync_playwright

        cls.playwright = sync_playwright().start()
        cls.browser = launch_browser(cls.playwright)
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

    def test_deepest_accepted_payload_reaches_the_page(self):
        with self.assertRaisesRegex(TemplateError, r"^data\.deep: unknown field$"):
            render_template(self.page, nested(MAX_DEPTH))

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
        self.assert_template_error(ticket(fields=[{"label": "a", "value": "b"}] * 11),
                                   r"^data\.fields: expected at most 10 items$")
        self.assert_template_error(ticket(qr={"text": "https://x.io/a\u2192b"}),
                                   r"^data\.qr\.text: expected ASCII \(percent-encode the URL\)$")

    def test_blank_visible_text_is_refused(self):
        for data, field in (
            ({"id": ""}, "id"),
            ({"title": " "}, "title"),
            ({"kind": " "}, "kind"),
            ({"time": ""}, "time"),
            ({"status": {"from": "OPEN", "to": ""}}, r"status\.to"),
            ({"fields": [{"label": "\u200b", "value": "b"}]}, r"fields\[0\]\.label"),
            ({"comment": {"text": "c", "author": " "}}, r"comment\.author"),
            ({"qr": {"text": ""}}, r"qr\.text"),
            ({"qr": {"text": "x", "lines": ["a", " "]}}, r"qr\.lines\[1\]"),
        ):
            with self.subTest(field), self.assertRaisesRegex(TemplateError, rf"^data\.{field}: expected non-blank text$"):
                render_template(self.page, ticket(**data))

    def test_text_past_its_cap_is_refused(self):
        widest = widest_ticket("W")["data"]
        for data, field, cap in (
            ({"kind": "W" * 17}, "kind", 16),
            ({"time": "W" * 9}, "time", 8),
            ({"id": "W" * 17}, "id", 16),
            ({"title": "W" * 121}, "title", 120),
            ({"status": {"from": "W" * 25, "to": "W"}}, r"status\.from", 24),
            ({"fields": [{"label": "W" * 17, "value": "W"}]}, r"fields\[0\]\.label", 16),
            ({"fields": [{"label": "W", "value": "W" * 33}]}, r"fields\[0\]\.value", 32),
            ({"comment": {"text": "W" * 281}}, r"comment\.text", 280),
            ({"comment": {"text": "W", "author": "W" * 33}}, r"comment\.author", 32),
            ({"qr": {**widest["qr"], "lines": ["W" * 41]}}, r"qr\.lines\[0\]", 40),
        ):
            with self.subTest(field), self.assertRaisesRegex(TemplateError, rf"^data\.{field}: expected at most {cap} characters$"):
                render_template(self.page, ticket(**data))

    def test_worst_case_fits_under_the_length_limit(self):
        for glyph in ("W", "\u6f22"):
            with self.subTest(glyph):
                image = render_template(self.page, widest_ticket(glyph))
                self.assertEqual(image.width, 384)
                self.assertLess(image.height, 4000)

    def test_component_that_throws_is_caught_by_the_error_boundary(self):
        with self.failing_transition():
            self.assert_template_error(TICKET, '^template "ticket" failed to render: boom$')

    def test_server_fault_is_not_a_template_error(self):
        with self.failing_transition(SERVER_FAULT):
            with self.assertRaisesRegex(RuntimeError, "^server fault: database down$") as caught:
                render_template(self.page, TICKET)
        self.assertNotIsInstance(caught.exception, TemplateError)
        render_template(self.page, TICKET)

    def test_parse_bug_is_a_server_fault(self):
        # Only validate.ts's object() calls Object.hasOwn: a throw there stands in for a bug in parse.
        self.page.evaluate("""() => {
          window.originalHasOwn = Object.hasOwn;
          Object.hasOwn = () => { throw new TypeError('parse broke'); };
        }""")
        try:
            with self.assertRaisesRegex(RuntimeError, "^server fault: parse broke$") as caught:
                render_template(self.page, TICKET)
        finally:
            self.page.evaluate("() => { Object.hasOwn = window.originalHasOwn; }")
        self.assertNotIsInstance(caught.exception, TemplateError)
        render_template(self.page, TICKET)

    def test_font_that_does_not_load_is_a_server_fault(self):
        # focus and agenda load their faces on the first render, so a patch after the page opens is in time.
        failures = {
            "missing": "() => { document.fonts.load = () => Promise.resolve([]); }",
            "rejected": "() => { document.fonts.load = () => Promise.reject(new DOMException('blocked', 'NetworkError')); }",
        }
        for name, faces in (("focus", "fonts 900 79px Archivo, .*"), ("agenda", 'font 700 16px "IBM Plex Mono"')):
            payload = json.loads((ROOT / "samples" / "templates" / f"{name}.json").read_text(encoding="utf-8"))
            for failure, patch in failures.items():
                page = open_render_page(self.browser)
                try:
                    page.evaluate(patch)
                    with self.subTest(f"{name} {failure}"), self.assertRaisesRegex(RuntimeError, f"^server fault: {faces} did not load$") as caught:
                        render_template(page, payload)
                    self.assertNotIsInstance(caught.exception, TemplateError)
                finally:
                    page.close()

    def test_effect_that_throws_fails_the_render(self):
        with self.failing_transition(EFFECT_THROWS):
            self.assert_template_error(TICKET, '^template "ticket" failed to render: effect boom$')
        render_template(self.page, TICKET)

    def test_render_that_never_settles_times_out(self):
        with self.failing_transition(NEVER_SETTLES):
            self.assert_template_error(TICKET, "^render did not finish within 3000 ms$")
        render_template(self.page, TICKET)

    def test_qr_is_drawn_square_on_whole_modules(self):
        def qr():
            image = render_template(self.page, TICKET)
            box = self.page.evaluate("""() => {
              const canvas = document.querySelector('#receipt canvas');
              const r = canvas.getBoundingClientRect(), origin = document.querySelector('#receipt').getBoundingClientRect();
              return { x: r.left - origin.left, y: r.top - origin.top, width: r.width, height: r.height,
                       pixels: canvas.width, rows: canvas.height };
            }""")
            region = image.crop((box["x"], box["y"], box["x"] + box["width"], box["y"] + box["height"]))
            return box, region

        box, region = qr()
        # The sample URL encodes as QR version 3: 29 modules, 4 quiet modules a side, 3 dots each.
        self.assertEqual((box["width"], box["height"], box["pixels"], box["rows"]), (111, 111, 111, 111))
        self.assertEqual((box["x"], box["y"]), (int(box["x"]), int(box["y"])))
        self.assertIsNotNone(region.convert("L").point(lambda value: 255 - value).getbbox(), "blank QR")
        self.assertEqual(qr()[1].tobytes(), region.tobytes())
        self.assertEqual(region.size, (111, 111))

    def test_layout_that_changes_after_the_render_fails(self):
        with self.failing_transition(KEEPS_GROWING):
            self.assert_template_error(TICKET, r"^render was still changing layout \(measured \d+ dots, then \d+\)$")
        render_template(self.page, TICKET)

    def test_system_fallback_face_is_the_same_at_capture(self):
        # Cyrillic is missing from the bundled fonts; the system face drawing it decides the wrapping.
        for attempt in range(3):
            page = open_render_page(self.browser)
            try:
                with self.subTest(attempt), self.failing_transition(
                        BOX % "{ style: { width: 384, fontWeight: 700 } }, '\u0428\u0428\u0428\u0428\u0428 '.repeat(12)", page):
                    image = render_template(page, TICKET)
                    self.assertEqual(image.height, page.evaluate("Math.ceil(document.querySelector('#receipt').getBoundingClientRect().height)"))
            finally:
                page.close()

    def test_fractional_length_renders(self):
        for height in (10.3, 10.7):
            with self.subTest(height), self.failing_transition(BOX % f"{{ style: {{ height: {height} }} }}"):
                render_template(self.page, TICKET)

    def test_layout_that_changes_during_the_screenshot_fails(self):
        locator = self.page.locator

        def grows_after_capture(selector):
            def screenshot(**kwargs):
                image = locator(selector).screenshot(**kwargs)
                self.page.evaluate(GROW)
                return image
            return mock.Mock(screenshot=screenshot)

        with mock.patch.object(self.page, "locator", side_effect=grows_after_capture):
            self.assert_template_error(TICKET, r"^render was still changing layout \(measured (\d+) dots, then (?!\1)\d+\)$")
        render_template(self.page, TICKET)

    def test_too_tall_fails_before_the_screenshot(self):
        with mock.patch.object(self.page, "locator", side_effect=AssertionError("screenshot taken")):
            self.assert_template_error(TICKET, r"^the receipt would print \d+\.\d cm long; the limit is 1\.25 cm$",
                                       max_height_dots=100)

    def test_landscape_render_is_rotated_onto_the_paper(self):
        with self.landscape_page() as page:
            image = render_template(page, SHORT_TICKET)
            height = page.evaluate("document.querySelector('#receipt').offsetHeight")
        self.assertEqual(height, 384)
        self.assertEqual((image.mode, image.width), ("1", 384))
        self.assertGreater(image.height, 384)
        # Clockwise: the HeaderBar (top of the layout) lands on the right edge, the feed at the end.
        self.assertEqual({image.getpixel((381, y)) for y in range(100)}, {0}, "header bar not on the right edge")
        self.assertNotEqual({image.getpixel((2, y)) for y in range(100)}, {0})
        self.assertIsNone(image.crop((0, image.height - 56, 384, image.height)).convert("L")
                          .point(lambda value: 255 - value).getbbox(), "feed not at the end")

    def test_clipped_cell_fails(self):
        with self.failing_transition(BOX % "{ className: 'rp-barrow-v', style: { width: 52 } }, '123,456,789'"):
            self.assert_template_error(TICKET, r'^text does not fit: "123,456,789" is wider than its 52px cell$')
        with self.failing_transition(BOX % "{ style: { height: 24, overflow: 'hidden' } }, 'word '.repeat(100)"):
            self.assert_template_error(TICKET, r'^text does not fit: "word word .*" is taller than its 24px cell$')
        with self.failing_transition(BOX % "{ style: { height: 40, lineHeight: '24px', whiteSpace: 'pre', overflow: 'hidden' } }, 'ONE\\nTWO'"):
            self.assert_template_error(TICKET, r'^text does not fit: "ONE TWO" is taller than its 40px cell$')
        with self.failing_transition(BOX % "{ style: { height: 0, overflow: 'hidden' } }, 'GONE'"):
            self.assert_template_error(TICKET, r'^text does not fit: "GONE" is taller than its 0px cell$')

    def test_text_mode_lines_that_fill_the_paper_fit(self):
        text_mode = "() => window.React.createElement(window.Thermal.TextMode, { lines: %s })"
        with self.failing_transition(text_mode % "['x'.repeat(32), { text: 'D'.repeat(16), double: true, reverse: true }]"):
            render_template(self.page, TICKET)
        with self.failing_transition(text_mode % "['ONE\\nTWO']"):
            self.assert_template_error(TICKET, r'^text does not fit: "ONE TWO" is taller than its 24px cell$')

    def test_text_spilling_out_of_its_cell_fails(self):
        with self.failing_transition(BOX % "{ style: { width: 52, whiteSpace: 'nowrap' } }, 'x'.repeat(10)"):
            self.assert_template_error(TICKET, r'^text does not fit: "xxxxxxxxxx" is wider than its 52px cell$')
        with self.failing_transition(BOX % "{ style: { width: 52, whiteSpace: 'nowrap' } }, 'x'.repeat(60)"):
            self.assert_template_error(TICKET, rf'^content runs past the paper edge: "{"x" * 39}\u2026"$')

    def test_content_past_the_paper_edge_fails(self):
        with self.failing_transition(BOX % "{ style: { width: 420 } }, 'WIDE'"):
            self.assert_template_error(TICKET, r'^content runs past the paper edge: "WIDE"$')
        with self.failing_transition(BOX % "{ className: 'rp-fill-solid', style: { width: 400, height: 8 } }"):
            self.assert_template_error(TICKET, r'^content runs past the paper edge: <div class="rp-fill-solid">$')

    def test_landscape_edge_is_the_bottom_of_the_layout(self):
        with self.landscape_page() as page:
            # Wider than the paper is the length of a landscape print; taller is past its edge.
            render_template(page, ticket(title="A title much wider than the paper " * 3, fields=None, comment=None, qr=None))
            with self.assertRaisesRegex(TemplateError, r'^content runs past the paper edge: "TICKET UPDATE'):
                render_template(page, TICKET)
            with self.failing_transition(BOX % "{ style: { width: 60, height: 20 } }, 'word '.repeat(80)", page):
                with self.assertRaisesRegex(TemplateError, r'^content runs past the paper edge: "word word '):
                    render_template(page, SHORT_TICKET)

    @contextlib.contextmanager
    def landscape_page(self):
        page = open_render_page(self.browser)
        try:
            render_template(page, SHORT_TICKET)
            self.assertEqual(page.evaluate("document.querySelector('#receipt').dataset.orientation"), "portrait")
            page.evaluate("""() => {
              const render = window.renderTemplate;
              window.renderTemplate = async (payload) => {
                await render(payload);
                document.querySelector('#receipt').dataset.orientation = 'landscape';
              };
            }""")
            yield page
        finally:
            page.close()

    @contextlib.contextmanager
    def failing_transition(self, component="() => { throw new Error('boom'); }", page=None):
        page = page or self.page
        transition = page.evaluate_handle("() => window.Thermal.Transition")
        page.evaluate(f"() => {{ window.Thermal.Transition = {component}; }}")
        try:
            yield
        finally:
            page.evaluate("(original) => { window.Thermal.Transition = original; }", transition)


class CliTest(unittest.TestCase):
    """print_template.py reports sender errors as one line, without a traceback."""

    @classmethod
    def setUpClass(cls):
        build_web()

    def run_cli(self, payload, artifact_dir, *flags):
        path = Path(artifact_dir) / "payload.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(ROOT / "src" / "scripts" / "print_template.py"), str(path),
             "--no-print", "--no-build", "--artifact-dir", artifact_dir, *flags],
            capture_output=True, text=True, check=False,
        )

    def test_sample_writes_a_png(self):
        with tempfile.TemporaryDirectory() as artifact_dir:
            result = self.run_cli(TICKET, artifact_dir)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((Path(artifact_dir) / "ticket.png").is_file())

    def test_text_writes_the_framed_job(self):
        build = json.loads((ROOT / "samples" / "templates" / "build.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as artifact_dir:
            result = self.run_cli(build, artifact_dir, "--text")
            self.assertEqual(result.returncode, 0, result.stderr)
            job = (Path(artifact_dir) / "build.bin").read_bytes()
        self.assertTrue(job.startswith(b"\x1b@\x1c."), job[:8])
        self.assertTrue(job.endswith(b" ci.local/b/1184\n\x1b2\n\n\n"), job[-24:])

    def test_text_refuses_a_template_without_text_mode(self):
        with tempfile.TemporaryDirectory() as artifact_dir:
            result = self.run_cli(TICKET, artifact_dir, "--text")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, 'ERROR: template "ticket" has no text mode\n')

    def test_template_error_is_one_line(self):
        with tempfile.TemporaryDirectory() as artifact_dir:
            result = self.run_cli({"template": "nope", "schemaVersion": 1, "data": {}}, artifact_dir)
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stderr, r'^ERROR: unknown template "nope"; known: .*\n$')


if __name__ == "__main__":
    unittest.main()
