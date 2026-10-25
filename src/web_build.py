"""Build web/dist with `npm run build`."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def build_web(web_dir: Path) -> None:
    if not (web_dir / "node_modules").is_dir():
        raise RuntimeError(f"Missing {web_dir / 'node_modules'}. Run: cd web && npm install")
    if not shutil.which("npm"):
        raise RuntimeError("npm not found on PATH; install Node.js or run `cd web && npm run build` manually.")
    proc = subprocess.run(["npm", "run", "build"], cwd=web_dir, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        out = (proc.stdout or "") + (proc.stderr or "")
        raise RuntimeError(f"`npm run build` in {web_dir} failed (exit {proc.returncode}).\n{out.strip() or '(no output)'}")
