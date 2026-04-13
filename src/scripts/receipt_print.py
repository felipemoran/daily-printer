"""
Render a JSON payload through the Vite receipt UI, screenshot, optionally print.

Full reference: docs/feature-receipt-print-cli.md

Prerequisites:
  cd web && npm install   (each run runs npm run build unless --no-build)
  uv run playwright install chromium

Example:
  uv run python src/scripts/receipt_print.py samples/receipt-sample.json --no-print
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC = _PROJECT_ROOT / "src"
sys.path.insert(0, str(_SRC))

from printer import PRINT_WIDTH_DOTS, open_printer  # noqa: E402
from raster_capture import screenshot_receipt_dist  # noqa: E402
from raster_split import split_raster_vertical  # noqa: E402
from receipt_image import prepare_for_escpos  # noqa: E402

DEFAULT_MAX_HEIGHT_PX = 4000  # ~50 cm at 8 dots/mm; tune with physical tests


def _run_web_build(web_dir: Path) -> None:
    if not (web_dir / "node_modules").is_dir():
        raise RuntimeError(
            f"Missing {web_dir / 'node_modules'}. Run: cd web && npm install"
        )
    if not shutil.which("npm"):
        raise RuntimeError(
            "npm not found on PATH; install Node.js or run `cd web && npm run build` manually."
        )
    proc = subprocess.run(
        ["npm", "run", "build"],
        cwd=web_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        out = (proc.stdout or "") + (proc.stderr or "")
        raise RuntimeError(
            f"`npm run build` in {web_dir} failed (exit {proc.returncode}).\n{out.strip() or '(no output)'}"
        )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Receipt: JSON → PNG → ESC/POS")
    p.add_argument(
        "payload_json",
        type=Path,
        help="Path to receipt payload JSON (see samples/receipt-sample.json)",
    )
    p.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="Directory for payload copy, PNG, preview.txt (default: artifacts/<utc-timestamp>)",
    )
    p.add_argument(
        "--no-print",
        action="store_true",
        help="Skip printer; only write artifacts",
    )
    p.add_argument(
        "--dither",
        action="store_true",
        help="Use Floyd–Steinberg dithering when converting to 1-bit",
    )
    p.add_argument(
        "--device-scale-factor",
        type=float,
        default=1.0,
        help="Playwright deviceScaleFactor (e.g. 2 for sharper captures)",
    )
    p.add_argument(
        "--max-height-px",
        type=int,
        default=DEFAULT_MAX_HEIGHT_PX,
        help="Future: split rasters taller than this (stub only for now)",
    )
    p.add_argument(
        "--no-build",
        action="store_true",
        help="Skip `npm run build`; use existing web/dist (faster when UI is unchanged)",
    )
    p.add_argument(
        "--build",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    payload_path = args.payload_json.resolve()
    if not payload_path.is_file():
        print(f"ERROR: payload file not found: {payload_path}", file=sys.stderr)
        sys.exit(1)

    try:
        json.loads(payload_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    web_dir = (_PROJECT_ROOT / "web").resolve()
    dist_dir = (web_dir / "dist").resolve()
    if not args.no_build:
        try:
            _run_web_build(web_dir)
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    if not (dist_dir / "index.html").is_file():
        print(
            "ERROR: web/dist/index.html missing. Build the receipt app first, e.g.:\n"
            "  cd web && npm install && npm run build\n"
            "Or omit --no-build so this tool runs the build for you.",
            file=sys.stderr,
        )
        sys.exit(1)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_dir = (
        args.artifact_dir.resolve()
        if args.artifact_dir
        else (_PROJECT_ROOT / "artifacts" / stamp).resolve()
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(payload_path, artifact_dir / "payload.json")
    shutil.copy2(payload_path, dist_dir / "payload.json")

    out_png = artifact_dir / "receipt.png"
    try:
        capture_url = screenshot_receipt_dist(
            dist_dir,
            out_png=out_png,
            device_scale_factor=args.device_scale_factor,
        )
    except Exception as e:
        print(f"ERROR: screenshot failed: {e}", file=sys.stderr)
        sys.exit(1)

    preview_txt = artifact_dir / "preview.txt"
    preview_txt.write_text(
        "\n".join(
            [
                f"capture_url={capture_url}",
                f"payload_json={artifact_dir / 'payload.json'}",
                "",
                "Replay in a browser: copy payload.json to web/dist/, run a static server",
                "from web/dist (e.g. `python -m http.server 8765`) and open:",
                "  http://127.0.0.1:8765/index.html",
                "",
                "Or: cd web && npm run dev  — use web/public/payload.json for local edits.",
            ]
        ),
        encoding="utf-8",
    )

    try:
        bitmap = prepare_for_escpos(
            out_png,
            target_width=PRINT_WIDTH_DOTS,
            dither=args.dither,
        )
    except Exception as e:
        print(f"ERROR: image prepare failed: {e}", file=sys.stderr)
        sys.exit(1)

    strips = split_raster_vertical(bitmap, args.max_height_px)

    if args.no_print:
        print(f"Artifacts: {artifact_dir}")
        return

    try:
        with open_printer() as p:
            for strip in strips:
                p.image(strip, center=False)
            p.ln(3)
    except SystemExit:
        raise
    except Exception as e:
        print(f"ERROR: print failed: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Printed ({len(strips)} strip(s)). Artifacts: {artifact_dir}")


if __name__ == "__main__":
    main()
