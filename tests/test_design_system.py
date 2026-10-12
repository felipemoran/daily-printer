import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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


if __name__ == "__main__":
    unittest.main()
