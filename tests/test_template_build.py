import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from tests.web_build import build_web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ticket_templates import TemplateError, open_render_page, render_template  # noqa: E402

SAMPLE = json.loads((ROOT / "samples" / "templates" / "build.json").read_text(encoding="utf-8"))
LINES_MODULE = ROOT / "web" / "src" / "templates" / "textmode-lines.ts"

# Node strips the types from the .ts module, so these tests call the same buildLines the template renders.
LINES_JS = f"""
import {{ buildLines }} from {json.dumps(LINES_MODULE.as_uri())};
let input = '';
for await (const chunk of process.stdin) input += chunk;
process.stdout.write(JSON.stringify(buildLines(JSON.parse(input))));
"""

DOM_LINES = """() => [...document.querySelectorAll('#receipt .rp-textmode > div')].map((div) => ({
  text: div.textContent, double: div.classList.contains('rp-tm-double'), reverse: div.classList.contains('rp-tm-inv'),
}))"""

# Every list at its cap and every string at its limit. Fifteen-letter words wrap one per line: the most lines.
WORST = {
    "template": "build",
    "schemaVersion": 1,
    "data": {
        "name": "W" * 12,
        "number": 9999999,
        "since": 9999999,
        "branch": "W" * 80,
        "commit": "W" * 80,
        "start": "W" * 40,
        "duration": "W" * 40,
        "status": "failed",
        "stages": [{"name": "W" * 80, "time": "W" * 40, "status": "fail"}] * 12,
        "suites": [{"name": "W" * 80, "seconds": 359999.9}] * 10,
        "failures": [{"spec": "W" * 80, "reason": "W" * 40, "title": ("W" * 15 + " ") * 7 + "W" * 8}] * 8,
        "commits": 9999999,
        "url": "W" * 200,
    },
}


def build(**data):
    payload = copy.deepcopy(SAMPLE)
    payload["data"].update(data)
    return payload


def lines(payload):
    result = subprocess.run(
        ["node", "--input-type=module", "-e", LINES_JS],
        input=json.dumps(payload["data"]), capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def texts(payload):
    return [line["text"] for line in lines(payload)]


class BuildLinesTest(unittest.TestCase):
    def test_sample_is_strip_1h(self):
        self.assertEqual(texts(SAMPLE), [
            "=" * 32,
            "      NIGHTLY BUILD  #1184",
            "=" * 32,
            " branch main     commit 9f3c2ab",
            " start  02:00    took   14m22s",
            "-" * 32,
            " STAGE             TIME  STATUS",
            " lint              0:41  [ OK ]",
            " unit tests        6:12  [ OK ]",
            " integration       5:03  [FAIL]",
            " build images      -:--  [SKIP]",
            "-" * 32,
            "  BUILD FAILED  ",
            "-" * 32,
            " SUITE DURATION",
            " api    █████████████░░░   4:12",
            " web    ███████░░░░░░░░░   2:20",
            " worker ████░░░░░░░░░░░░   1:15",
            " e2e    ████████████████   5:03",
            "-" * 32,
            " FAILURES (2)",
            " > checkout.spec        TIMEOUT",
            '   "applies coupon"',
            " > refunds.spec        HTTP 500",
            '   "partial refund"',
            "-" * 32,
            " 3 commits since #1183",
            "=" * 32,
            " ci.local/b/1184",
        ])

    def test_every_line_fits_its_columns(self):
        for line in lines(WORST):
            with self.subTest(line["text"]):
                self.assertLessEqual(len(line["text"]), 16 if line.get("double") else 32)

    def test_stage_columns_align(self):
        stages = [
            {"name": "x", "time": "0:01", "status": "ok"},
            {"name": "a much longer stage name", "time": "12:34", "status": "fail"},
            {"name": "mid name", "time": "-:--", "status": "skip"},
        ]
        rows = [text for text in texts(build(stages=stages)) if text.endswith(("]", "STATUS"))]
        self.assertEqual(len(rows), 4)
        self.assertEqual({len(row) for row in rows}, {31})
        self.assertEqual([row[18:23] for row in rows], [" TIME", " 0:01", "12:34", " -:--"])
        self.assertEqual([row[25:] for row in rows], ["STATUS", "[ OK ]", "[FAIL]", "[SKIP]"])
        self.assertEqual(rows[2][:18], " a much longer s~ ")

    def test_long_values_truncate_with_the_marker(self):
        result = texts(build(branch="feature/long-branch", commit="9f3c2ab0d1e2"))
        self.assertEqual(result[3], " branch feature~ commit 9f3c2a~")

    def test_long_urls_print_in_full(self):
        url = "https://ci.example.com/" + "b" * 97
        result = texts(build(url=url))
        printed = result[result.index("=" * 32, 3) + 1:]
        self.assertEqual(len(printed), 4)
        self.assertEqual({line[0] for line in printed}, {" "})
        self.assertEqual("".join(line[1:] for line in printed), url)

    def test_since_prints_only_when_sent(self):
        self.assertIn(" 3 commits since #1183", texts(SAMPLE))
        payload = build(commits=1)
        del payload["data"]["since"]
        self.assertIn(" 1 commit", texts(payload))

    def test_name_heads_the_title(self):
        self.assertEqual(texts(build(name="Relé"))[1], "       RELE BUILD  #1184")
        payload = copy.deepcopy(SAMPLE)
        del payload["data"]["name"]
        self.assertEqual(texts(payload)[1], "          BUILD  #1184")
        self.assertEqual(texts(WORST)[1], "  WWWWWWWWWWWW BUILD  #9999999")
        self.assertIn(" 9999999 commits since #9999999", texts(WORST))

    def test_long_failure_titles_wrap(self):
        title = "applies the coupon to every line item of a mixed cart"
        result = texts(build(failures=[{"spec": "checkout.spec", "reason": "TIMEOUT", "title": title}]))
        start = result.index(" > checkout.spec        TIMEOUT") + 1
        wrapped = result[start:result.index("-" * 32, start)]
        self.assertGreater(len(wrapped), 1)
        for line in wrapped:
            self.assertTrue(line.startswith("   ") and len(line) <= 31, line)
        self.assertEqual(" ".join(line.strip() for line in wrapped), f'"{title}"')

    def test_bars_scale_to_the_longest_suite(self):
        result = texts(build(suites=[{"name": "a", "seconds": 100}, {"name": "b", "seconds": 50}, {"name": "c", "seconds": 0}]))
        bars = [text[8:24] for text in result if text.startswith((" a ", " b ", " c "))]
        self.assertEqual(bars, ["█" * 16, "█" * 8 + "░" * 8, "░" * 16])
        zero = texts(build(suites=[{"name": "a", "seconds": 0}, {"name": "b", "seconds": 0}]))
        self.assertEqual([text[8:24] for text in zero if text.startswith((" a ", " b "))], ["░" * 16] * 2)

    def test_durations_fit_their_cell(self):
        result = texts(build(suites=[{"name": "a", "seconds": 59.9}, {"name": "b", "seconds": 3599}, {"name": "c", "seconds": 359999}]))
        self.assertEqual([text[25:] for text in result if text.startswith((" a ", " b ", " c "))], ["  0:59", " 59:59", "99h59m"])

    def test_banner_shows_the_status(self):
        failed = [line for line in lines(SAMPLE) if line.get("double")]
        passed = [line for line in lines(build(status="passed")) if line.get("double")]
        self.assertEqual(failed, [{"text": "  BUILD FAILED  ", "double": True, "reverse": True}])
        self.assertEqual(passed, [{"text": "  BUILD PASSED  ", "double": True}])

    def test_text_outside_ascii_prints_as_ascii(self):
        result = texts(build(branch="café\tvoilà", failures=[{"spec": "a.spec", "reason": "✗ 500", "title": "naïve ✓"}]))
        self.assertEqual(result[3], " branch cafe?vo~ commit 9f3c2ab")
        self.assertIn(" > a.spec" + " " * 17 + "? 500", result)
        self.assertIn('   "naive ?"', result)
        self.assertEqual(texts(build(commit="🔥🚀🎉"))[3][-3:], "???")

    def test_output_is_printable_ascii_or_bar_glyphs(self):
        allowed = {chr(code) for code in range(0x20, 0x7F)} | {"█", "░"}
        odd = build(name="Ünïcode", branch="🔥\x00\x1b", failures=[{"spec": "日本", "reason": "\u200b", "title": "e\u0301\n"}])
        for payload in (WORST, odd):
            self.assertLessEqual(set("".join(texts(payload))), allowed)


class BuildRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_web()
        from playwright.sync_api import sync_playwright

        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)
        cls.page = open_render_page(cls.browser)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def test_preview_prints_the_lines_uncut(self):
        for payload in (SAMPLE, WORST, build(status="passed")):
            with self.subTest(payload["data"]["status"]):
                render_template(self.page, payload)
                expected = [{"double": False, "reverse": False, **line} for line in lines(payload)]
                self.assertEqual(self.page.evaluate(DOM_LINES), expected)

    def test_worst_case_renders_under_the_limit(self):
        image = render_template(self.page, WORST)
        self.assertEqual(image.width, 384)
        self.assertLess(image.height, 4000)

    def test_refuses_bad_data(self):
        stage = {"name": "lint", "time": "0:41", "status": "ok"}
        cases = (
            (build(status="broken"), r"^data\.status: expected one of passed, failed$"),
            (build(stages=[{**stage, "status": "OK"}]), r"^data\.stages\[0\]\.status: expected one of ok, fail, skip$"),
            (build(stages=[stage] * 13), r"^data\.stages: expected at most 12 items$"),
            (build(suites=[{"name": "a", "seconds": 1}] * 11), r"^data\.suites: expected at most 10 items$"),
            (build(failures=[{"spec": "a", "reason": "b", "title": "c"}] * 9), r"^data\.failures: expected at most 8 items$"),
            (build(suites=[{"name": "a", "seconds": -1}]), r"^data\.suites\[0\]\.seconds: expected seconds from 0 to 359999$"),
            (build(suites=[{"name": "a", "seconds": 360000}]), r"^data\.suites\[0\]\.seconds: expected seconds from 0 to 359999$"),
            (build(number=0), r"^data\.number: expected a whole number from 1 to 9999999$"),
            (build(number=1.5), r"^data\.number: expected a whole number from 1 to 9999999$"),
            (build(number=10000000), r"^data\.number: expected a whole number from 1 to 9999999$"),
            (build(since=0), r"^data\.since: expected a whole number from 1 to 9999999$"),
            (build(since=10000000), r"^data\.since: expected a whole number from 1 to 9999999$"),
            (build(name="W" * 13), r"^data\.name: expected at most 12 characters$"),
            (build(name=" "), r"^data\.name: expected non-blank text$"),
            (build(commits=-1), r"^data\.commits: expected a whole number from 0 to 9999999$"),
            (build(commits=10000000), r"^data\.commits: expected a whole number from 0 to 9999999$"),
            (build(branch=" "), r"^data\.branch: expected non-blank text$"),
            (build(url="W" * 201), r"^data\.url: expected at most 200 characters$"),
            (build(failures=[{"spec": "a", "reason": "b", "title": "W" * 121}]), r"^data\.failures\[0\]\.title: expected at most 120"),
            (build(extra=1), r"^data\.extra: unknown field$"),
        )
        for payload, pattern in cases:
            with self.subTest(pattern), self.assertRaisesRegex(TemplateError, pattern):
                render_template(self.page, payload)


if __name__ == "__main__":
    unittest.main()
