"""
Render a template payload ({"template", "schemaVersion", "data"}) and print it.

Reference: docs/feature-ticket-templates.md

Example:
  uv run src/scripts/print_template.py samples/templates/ticket.json --no-print
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from playwright.sync_api import sync_playwright  # noqa: E402

from printer import open_printer  # noqa: E402
from receipt_print import _run_web_build  # noqa: E402
from ticket_templates import TemplateError, open_render_page, render_template  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a template payload to 1-bit and print it.")
    parser.add_argument("payload_json", type=Path, help="e.g. samples/templates/ticket.json")
    parser.add_argument("--no-print", action="store_true", help="only write the PNG")
    parser.add_argument("--no-build", action="store_true", help="skip `npm run build`; use the existing web/dist")
    parser.add_argument("--artifact-dir", type=Path, default=None, help="default: artifacts/template-<utc-timestamp>")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        payload = json.loads(args.payload_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        sys.exit(f"ERROR: cannot read {args.payload_json}: {error}")
    if not args.no_build:
        try:
            _run_web_build(_PROJECT_ROOT / "web")
        except RuntimeError as error:
            sys.exit(f"ERROR: {error}")

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                bitmap = render_template(open_render_page(browser), payload)
            finally:
                browser.close()
    except (TemplateError, RuntimeError) as error:
        sys.exit(f"ERROR: {error}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_dir = (args.artifact_dir or _PROJECT_ROOT / "artifacts" / f"template-{stamp}").resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    out_png = artifact_dir / f"{payload['template']}.png"
    bitmap.save(out_png)
    print(f"Rendered {bitmap.width}x{bitmap.height}: {out_png}")
    if args.no_print:
        return

    try:
        with open_printer() as printer:
            printer.image(bitmap, center=False)
            printer.ln(3)
    except SystemExit:
        raise
    except Exception as error:
        sys.exit(f"ERROR: print failed: {error}")
    print("Printed.")


if __name__ == "__main__":
    main()
