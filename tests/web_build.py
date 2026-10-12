import functools
import subprocess
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"


@functools.cache
def _build():
    subprocess.run(["npm", "run", "build"], cwd=WEB, check=True, capture_output=True)


def build_web():
    """Build web/dist once per process; skip the caller when web dependencies are missing."""
    if not (WEB / "node_modules").is_dir():
        raise unittest.SkipTest("needs web dependencies: make setup-web")
    _build()
