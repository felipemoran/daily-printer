import functools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import web_build  # noqa: E402


@functools.cache
def build_web():
    """Build web/dist once per process."""
    if not (ROOT / "web" / "node_modules").is_dir():
        raise RuntimeError("web dependencies missing: run make setup-web")
    web_build.build_web(ROOT / "web")
