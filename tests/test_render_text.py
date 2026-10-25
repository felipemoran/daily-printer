import sys
import unittest
from pathlib import Path

from tests.web_build import build_web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from test_template_build import DOM_LINES, SAMPLE, WORST, build  # noqa: E402
from ticket_templates import TemplateError, open_render_page, render_template, render_text  # noqa: E402

START = b"\x1c." + b"\x1b3\x18" + b"\x1bt\x00"
END = b"\x1b2"
WRAPPERS = {"reverse": (b"\x1dB\x01", b"\x1dB\x00"), "double": (b"\x1d!\x11", b"\x1d!\x00")}
GLYPHS = {0xDB: "█", 0xB0: "░"}
TEMPLATE_LINES = "(payload) => window.templateLines(payload)"


def setUpModule():
    build_web()


def decode(body: bytes):
    """The lines a body prints, as {text, double, reverse}; fails on any byte outside the known framing."""
    assert body.startswith(START) and body.endswith(b"\n" + END), body[:8] + b"..." + body[-8:]
    lines = []
    for raw in body[len(START):-len(END)].split(b"\n")[:-1]:
        line = {}
        for flag, (on, off) in WRAPPERS.items():
            line[flag] = raw.startswith(on) and raw.endswith(off)
            if line[flag]:
                raw = raw[len(on):-len(off)]
        if any(not (0x20 <= byte <= 0x7E or byte in GLYPHS) for byte in raw):
            raise AssertionError(f"control byte in {raw!r}")
        lines.append({"text": "".join(GLYPHS.get(byte, chr(byte)) for byte in raw), **line})
    return lines


class RenderTextTest(unittest.TestCase):
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

    def test_text_breaks_lines_like_the_preview(self):
        for name, payload in (("sample", SAMPLE), ("worst", WORST), ("passed", build(status="passed"))):
            with self.subTest(name):
                printed = decode(render_text(self.page, payload))
                model = self.page.evaluate(TEMPLATE_LINES, payload)
                self.assertEqual(printed, [{"double": False, "reverse": False, **line} for line in model])
                render_template(self.page, payload)
                self.assertEqual(printed, self.page.evaluate(DOM_LINES))

    def test_body_framing(self):
        body = render_text(self.page, SAMPLE)
        self.assertTrue(body.startswith(START))
        self.assertTrue(body.endswith(b" ci.local/b/1184\n" + END))
        self.assertNotIn(b"\x1b@", body)
        self.assertNotIn(b"\x1dV", body)
        self.assertNotIn(b"\x1bd", body)
        self.assertIn(b"\n\x1dB\x01\x1d!\x11  BUILD FAILED  \x1d!\x00\x1dB\x00\n", body)
        self.assertIn(b" api    " + b"\xdb" * 13 + b"\xb0" * 3 + b"   4:12\n", body)
        passed = render_text(self.page, build(status="passed"))
        self.assertIn(b"\n\x1d!\x11  BUILD PASSED  \x1d!\x00\n", passed)
        self.assertNotIn(b"\x1dB", passed)

    def test_sender_faults(self):
        cases = (
            ({"template": "nope", "schemaVersion": 1, "data": {}}, r'^unknown template "nope"; known: .*build'),
            ({"template": "ticket", "schemaVersion": 1, "data": {}}, r'^template "ticket" has no text mode$'),
            ({**SAMPLE, "schemaVersion": 2}, r'^template "build" expects schemaVersion 1, got 2$'),
            (build(status="broken"), r"^data\.status: expected one of passed, failed$"),
            ({**SAMPLE, "data": []}, r"^data: expected object$"),
        )
        for payload, pattern in cases:
            with self.subTest(pattern), self.assertRaisesRegex(TemplateError, pattern):
                render_text(self.page, payload)

    def test_any_fault_past_the_data_is_the_servers(self):
        # buildLines calls Math.max once; a throw there stands in for a fault in the line model.
        cases = (
            ("Math.max = () => { throw Object.assign(new Error('line model broke'), { name: 'ServerFault' }); }",
             "^server fault: line model broke$"),
            ("Math.max = () => { throw new TypeError('x is undefined'); }", "^server fault: x is undefined$"),
            ("delete window.templateLines", "^server fault: render.html has no templateLines; rebuild web/dist$"),
        )
        for patch, pattern in cases:
            with self.subTest(pattern):
                self.page.evaluate("() => { window.originals = { max: Math.max, lines: window.templateLines }; }")
                self.page.evaluate(f"() => {{ {patch}; }}")
                try:
                    with self.assertRaisesRegex(RuntimeError, pattern) as caught:
                        render_text(self.page, SAMPLE)
                finally:
                    self.page.evaluate("() => { Math.max = window.originals.max; window.templateLines = window.originals.lines; }")
                self.assertNotIsInstance(caught.exception, TemplateError)
        self.assertTrue(render_text(self.page, SAMPLE).startswith(START))

if __name__ == "__main__":
    unittest.main()
