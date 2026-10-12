"""
Gather daily data, render through the receipt UI, and print.

This is the main entry point for the daily print workflow:
  1. Gather — fetch all configured data sources (Todoist, etc.) via src/gather.py
  2. Write  — save payload.json to the artifact directory and web/dist/
  3. Render — Playwright screenshots the Vite receipt app
  4. Print  — send the raster image to the ESC/POS printer

Artifacts written per run (in artifacts/<utc-timestamp>/):
  payload.json    — the data payload used for this run
  receipt.png     — the rendered receipt image
  print.png       — the 1-bit image sent to the printer
  preview.txt     — capture URL and replay instructions

Usage:
  uv run src/scripts/daily_print.py             # gather → render → print
  uv run src/scripts/daily_print.py --no-print  # gather → render (skip printer)
  uv run src/scripts/daily_print.py --no-build  # skip npm build (faster if UI unchanged)
  uv run src/scripts/daily_print.py --template  # print today's tasks on the `tasks` template
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC = _PROJECT_ROOT / "src"
sys.path.insert(0, str(_SRC))

from print_profile import DEFAULT_PROFILE, LEGACY_PROFILE, capture_options, load_gray, to_bitmap  # noqa: E402
from printer import open_printer  # noqa: E402
from raster_capture import capture_receipt  # noqa: E402
from raster_split import split_raster_vertical  # noqa: E402
from web_build import build_web  # noqa: E402

DEFAULT_MAX_HEIGHT_PX = 4000


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Gather daily data, render receipt, and print.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--no-print",
        action="store_true",
        help="Skip printer; only gather and write artifacts",
    )
    p.add_argument(
        "--no-build",
        action="store_true",
        help="Skip `npm run build`; use existing web/dist (faster when UI is unchanged)",
    )
    p.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="Directory for artifacts (default: artifacts/<utc-timestamp>)",
    )
    p.add_argument(
        "--template",
        action="store_true",
        help="print today's and overdue tasks on the `tasks` template instead of the receipt",
    )
    p.add_argument(
        "--legacy",
        action="store_true",
        help="pre-2026-10 raster: anti-aliased text, threshold, no erosion",
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
    )
    return p.parse_args()


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()

    args = _parse_args()

    # ---- 1. Gather ----------------------------------------------------------
    print("Gathering data…", flush=True)
    try:
        if args.template:
            from task_formatter import sections_to_payload
            from todoist_client import get_task_sections
            sections = get_task_sections()
            payload = sections_to_payload(sections)
        else:
            from gather import gather
            payload = gather()
    except Exception as e:
        print(f"ERROR: gather failed: {e}", file=sys.stderr)
        sys.exit(1)

    block_count = len(payload.get("blocks", []))
    print(f"  {block_count} block(s) collected", flush=True)

    # ---- 2. Build web UI ----------------------------------------------------
    web_dir = (_PROJECT_ROOT / "web").resolve()
    dist_dir = (web_dir / "dist").resolve()

    if not args.no_build:
        print("Building web UI…", flush=True)
        try:
            build_web(web_dir)
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

    if not (dist_dir / "index.html").is_file():
        print(
            "ERROR: web/dist/index.html missing.\n"
            "Run: cd web && npm install && npm run build\n"
            "Or omit --no-build so this script builds for you.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ---- 3. Write artifacts -------------------------------------------------
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_dir = (
        args.artifact_dir.resolve()
        if args.artifact_dir
        else (_PROJECT_ROOT / "artifacts" / stamp).resolve()
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)

    payload_text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    artifact_payload = artifact_dir / "payload.json"
    artifact_payload.write_text(payload_text, encoding="utf-8")
    (dist_dir / "payload.json").write_text(payload_text, encoding="utf-8")

    if args.template:
        from print_template import render_and_print
        from tasks_template import tasks_payload

        template_payload = tasks_payload(sections, datetime.now().astimezone())
        (artifact_dir / "tasks.json").write_text(json.dumps(template_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        render_and_print(template_payload, artifact_dir, args.no_print)
        return

    # ---- 4. Screenshot ------------------------------------------------------
    print("Rendering receipt…", flush=True)
    out_png = artifact_dir / "receipt.png"
    profile = LEGACY_PROFILE if args.legacy else DEFAULT_PROFILE
    try:
        capture_url, _ = capture_receipt(
            dist_dir,
            out_png=out_png,
            device_scale_factor=args.device_scale_factor,
            **capture_options(profile),
        )
    except Exception as e:
        print(f"ERROR: screenshot failed: {e}", file=sys.stderr)
        sys.exit(1)

    (artifact_dir / "preview.txt").write_text(
        "\n".join([
            f"capture_url={capture_url}",
            f"payload_json={artifact_payload}",
            f"receipt_png={out_png}",
            "",
            "Replay: copy payload.json to web/dist/, run a static server from web/dist/",
            "  python -m http.server 8765  →  http://127.0.0.1:8765/index.html",
            "",
            "Or: cd web && npm run dev  (uses web/public/payload.json)",
        ]),
        encoding="utf-8",
    )

    # ---- 5. Print -----------------------------------------------------------
    print("Preparing image…", flush=True)
    try:
        bitmap = to_bitmap(load_gray(out_png), profile)
        bitmap.save(artifact_dir / "print.png")
    except Exception as e:
        print(f"ERROR: image prepare failed: {e}", file=sys.stderr)
        sys.exit(1)

    if args.no_print:
        print(f"Done (skipped print). Artifacts: {artifact_dir}")
        return

    strips = split_raster_vertical(bitmap, args.max_height_px)

    print("Printing…", flush=True)
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
