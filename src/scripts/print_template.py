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

from playwright.sync_api import Error as PlaywrightError, sync_playwright  # noqa: E402

from printer import open_printer  # noqa: E402
from web_build import build_web  # noqa: E402
from ticket_templates import TemplateError, open_render_page, render_template  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a template payload to 1-bit and print it.")
    parser.add_argument("payload_json", type=Path, help="e.g. samples/templates/ticket.json")
    parser.add_argument("--no-print", action="store_true", help="only write the PNG")
    parser.add_argument("--no-build", action="store_true", help="skip `npm run build`; use the existing web/dist")
    parser.add_argument("--artifact-dir", type=Path, default=None, help="default: artifacts/template-<utc-timestamp>")
    return parser.parse_args()


def render_and_print(payload: dict, artifact_dir: Path, no_print: bool) -> None:
    """Render ``payload`` from the built web/dist, save ``<template>.png`` in ``artifact_dir``, then print. Exits with a one-line error."""
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                bitmap = render_template(open_render_page(browser), payload)
            finally:
                browser.close()
    except (TemplateError, RuntimeError) as error:
        sys.exit(f"ERROR: {error}")
    except PlaywrightError as error:
        hint = " Run: uv run playwright install chromium" if "Executable doesn't exist" in error.message else ""
        sys.exit(f"ERROR: browser failed: {error.message.splitlines()[0]}{hint}")

    artifact_dir = artifact_dir.resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    out_png = artifact_dir / f"{payload['template']}.png"
    bitmap.save(out_png)
    print(f"Rendered {bitmap.width}x{bitmap.height}: {out_png}")
    if no_print:
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


def main() -> None:
    args = _parse_args()
    try:
        payload = json.loads(args.payload_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        sys.exit(f"ERROR: cannot read {args.payload_json}: {error}")
    if not args.no_build:
        try:
            build_web(_PROJECT_ROOT / "web")
        except RuntimeError as error:
            sys.exit(f"ERROR: {error}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    render_and_print(payload, args.artifact_dir or _PROJECT_ROOT / "artifacts" / f"template-{stamp}", args.no_print)


if __name__ == "__main__":
    main()
