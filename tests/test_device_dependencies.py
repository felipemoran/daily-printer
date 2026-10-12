"""A device runs `uv run --script`, which installs only the dependencies in the script's inline metadata."""

import ast
import importlib.metadata
import os
import re
import shutil
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
SCRIPT = SRC / "scripts" / "print_device.py"
# The reference regex from PEP 723.
METADATA_BLOCK = re.compile(r"(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$")
REQUIREMENT = re.compile(r"^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[(?P<extras>[^\]]*)\])?")
NEVER_ON_DEVICE = {"playwright", "jwt"}
UV = shutil.which(os.environ.get("UV") or "uv")
# (module, import): why the device never needs it.
UNDECLARED_ALLOWED = {
    ("printer.py", "bleak"): "only printer._ble_find_and_send imports it, and the device never calls it",
}


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def script_metadata(path: Path) -> dict:
    blocks = [match for match in METADATA_BLOCK.finditer(path.read_text()) if match.group("type") == "script"]
    if len(blocks) != 1:
        raise ValueError(f"{path} has {len(blocks)} script metadata blocks, not 1")
    lines = blocks[0].group("content").splitlines(keepends=True)
    return tomllib.loads("".join(line[2:] if line.startswith("# ") else line[1:] for line in lines))


def imports(path: Path) -> set[str]:
    """Top-level names of every import in the file, inside functions too."""
    names = set()
    for node in ast.walk(ast.parse(path.read_text(), str(path))):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module != "__future__":
            names.add(node.module.split(".")[0])
    return names


def local_module(name: str) -> Path | None:
    # The script puts src/ on sys.path; Python adds the script's own folder.
    for folder in (SRC, SCRIPT.parent):
        if (folder / f"{name}.py").is_file():
            return folder / f"{name}.py"
    return None


def device_modules() -> list[Path]:
    """The script and every local module it reaches."""
    found, pending = [], [SCRIPT]
    while pending:
        path = pending.pop()
        if path in found:
            continue
        found.append(path)
        pending += [module for name in imports(path) if (module := local_module(name))]
    return found


def third_party(names: set[str]) -> set[str]:
    return {name for name in names if name not in sys.stdlib_module_names and local_module(name) is None}


def declared_distributions() -> set[str]:
    """Each dependency in the metadata, plus what its requested extras pull in."""
    declared = set()
    for requirement in script_metadata(SCRIPT)["dependencies"]:
        match = REQUIREMENT.match(requirement)
        declared.add(normalize(match.group("name")))
        for extra in filter(None, (part.strip() for part in (match.group("extras") or "").split(","))):
            for extra_requirement in importlib.metadata.requires(match.group("name")) or []:
                if re.search(rf"extra\s*==\s*['\"]{re.escape(extra)}['\"]", extra_requirement):
                    declared.add(normalize(REQUIREMENT.match(extra_requirement).group("name")))
    return declared


class DeviceDependenciesTest(unittest.TestCase):
    def test_device_path_is_the_script_and_the_modules_it_imports(self):
        self.assertEqual(
            {path.relative_to(SRC).as_posix() for path in device_modules()},
            {"scripts/print_device.py", "print_device.py", "fake_printer.py", "printer.py"},
        )

    def test_every_third_party_import_is_declared_in_the_script_metadata(self):
        distributions = importlib.metadata.packages_distributions()
        declared = declared_distributions()
        for path in device_modules():
            for name in sorted(third_party(imports(path))):
                if (path.name, name) in UNDECLARED_ALLOWED:
                    continue
                with self.subTest(module=path.name, imports=name):
                    self.assertIn(name, distributions, f"{name} is not installed, so it maps to no distribution")
                    self.assertTrue(
                        {normalize(dist) for dist in distributions[name]} & declared,
                        f"{path.relative_to(SRC.parent)} imports {name} ({', '.join(distributions[name])}), "
                        f"which the metadata in {SCRIPT.relative_to(SRC.parent)} does not declare",
                    )

    def test_playwright_and_jwt_are_never_imported_on_the_device_path(self):
        for path in device_modules():
            with self.subTest(module=path.name):
                self.assertFalse(imports(path) & NEVER_ON_DEVICE)

    def test_an_allowed_undeclared_import_never_runs_at_module_load(self):
        for module, name in UNDECLARED_ALLOWED:
            with self.subTest(module=module, imports=name):
                body = ast.parse(local_module(module.removesuffix(".py")).read_text()).body
                top_level = {alias.name.split(".")[0] for node in body if isinstance(node, ast.Import) for alias in node.names}
                top_level |= {node.module.split(".")[0] for node in body if isinstance(node, ast.ImportFrom) and node.module}
                self.assertNotIn(name, top_level, f"{module} imports {name} at load time, so a device would crash")

    @unittest.skipIf(UV is None, "uv is not installed, so the script lock cannot be checked")
    def test_script_lock_matches_the_script_metadata(self):
        result = subprocess.run([UV, "lock", "--script", str(SCRIPT), "--check"], capture_output=True, text=True)
        self.assertEqual(
            result.returncode, 0,
            f"{result.stderr}\nRun: uv lock --script {SCRIPT.relative_to(SRC.parent)}",
        )


if __name__ == "__main__":
    unittest.main()
