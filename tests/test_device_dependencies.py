"""A device runs `uv run --script`, which installs only the dependencies in the script's inline metadata."""

import ast
import importlib.metadata
import re
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


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def script_metadata(path: Path) -> dict:
    blocks = [match for match in METADATA_BLOCK.finditer(path.read_text()) if match.group("type") == "script"]
    if len(blocks) != 1:
        raise ValueError(f"{path} has {len(blocks)} script metadata blocks, not 1")
    lines = blocks[0].group("content").splitlines(keepends=True)
    return tomllib.loads("".join(line[2:] if line.startswith("# ") else line[1:] for line in lines))


class _Imports(ast.NodeVisitor):
    def __init__(self, at_load_only: bool) -> None:
        self.at_load_only = at_load_only
        self.names: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        self.names.update(alias.name.split(".")[0] for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level == 0 and node.module != "__future__":
            self.names.add(node.module.split(".")[0])

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if not self.at_load_only:
            self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef


def imports(path: Path, at_load_only: bool) -> set[str]:
    visitor = _Imports(at_load_only)
    visitor.visit(ast.parse(path.read_text(), str(path)))
    return visitor.names


def local_module(name: str) -> Path | None:
    # The script puts src/ on sys.path; Python adds the script's own folder.
    for folder in (SRC, SCRIPT.parent):
        if (folder / f"{name}.py").is_file():
            return folder / f"{name}.py"
    return None


def device_modules() -> list[Path]:
    """The script and every local module it reaches, lazy imports included."""
    found, pending = [], [SCRIPT]
    while pending:
        path = pending.pop()
        if path in found:
            continue
        found.append(path)
        pending += [module for name in imports(path, at_load_only=False) if (module := local_module(name))]
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

    def test_every_third_party_import_at_load_is_declared_in_the_script_metadata(self):
        distributions = importlib.metadata.packages_distributions()
        declared = declared_distributions()
        for path in device_modules():
            for name in sorted(third_party(imports(path, at_load_only=True))):
                with self.subTest(module=path.name, imports=name):
                    self.assertIn(name, distributions, f"{name} is not installed, so it maps to no distribution")
                    self.assertTrue(
                        {normalize(dist) for dist in distributions[name]} & declared,
                        f"{path.name} imports {name} ({', '.join(distributions[name])}), "
                        f"which the metadata in {SCRIPT.name} does not declare",
                    )

    def test_playwright_and_jwt_are_never_imported_on_the_device_path(self):
        for path in device_modules():
            with self.subTest(module=path.name):
                self.assertFalse(imports(path, at_load_only=False) & NEVER_ON_DEVICE)


if __name__ == "__main__":
    unittest.main()
