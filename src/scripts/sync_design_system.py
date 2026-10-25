"""
Mirror the Thermal design system from Claude Design, and regenerate the web files built from it.

design-system/ is a verbatim copy of the artifact's project/ folder; never edit it by hand.
Procedure: docs/feature-design-system.md.

Examples:
  uv run src/scripts/sync_design_system.py path/to/download/project   # replace the mirror, regenerate
  uv run src/scripts/sync_design_system.py                            # regenerate from the mirror
  uv run src/scripts/sync_design_system.py --check                    # exit 1 if generated files are stale
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIRROR = ROOT / "design-system"
GENERATED = ROOT / "web" / "src" / "thermal" / "generated"
NAMESPACE = "Thermal"  # web/src/thermal/index.ts reads window.Thermal

HEADER = "/* Generated from design-system/ by src/scripts/sync_design_system.py. Do not edit. */\n"
# Fonts are self-hosted (web/src/fonts.css): renders must not depend on the network.
_GOOGLE_FONTS_IMPORT = re.compile(r'^@import url\("https://fonts\.googleapis\.com/[^\n]*\n', re.MULTILINE)
_TYPE_PROPERTIES = {
    "fontSize": "font-size",
    "lineHeight": "line-height",
    "fontWeight": "font-weight",
    "fontStyle": "font-style",
    "letterSpacing": "letter-spacing",
}


class SyncError(Exception):
    pass


def _value(value, unit: str = "px") -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value}{unit}"
    alias = re.fullmatch(r"\{([A-Za-z0-9_.-]+)\}", value)
    return f"var(--{alias.group(1)})" if alias else value


def _type_value(key: str, value) -> str:
    if key == "fontWeight" or (key == "lineHeight" and isinstance(value, (int, float)) and value < 10):
        return _value(value, unit="")
    return _value(value)


def tokens_css(tokens: dict) -> str:
    """CSS custom properties and type classes, as the Claude Design page compiles tokens.json."""
    color = tokens.get("color", {})
    themes = color.get("themes", [])
    if len(themes) > 1:
        raise SyncError(f"tokens.json has {len(themes)} colour themes; the generator supports one")

    def color_value(value):
        if isinstance(value, dict):
            value = value[themes[0]["id"]]
        return _value(value)

    selector = f':root, [data-theme="{themes[0]["id"]}"]' if themes else ":root"
    lines = [HEADER, f"{selector} {{"]
    lines += [f"  --{t['name']}: {color_value(t['value'])};" for t in color.get("tokens", [])]
    lines += ["}", "", ":root {"]
    for family, body in tokens.items():
        if family in ("color", "type") or not isinstance(body, dict) or "tokens" not in body:
            continue
        lines += [f"  --{t['name']}: {_value(t['value'])};" for t in body["tokens"]]
    type_ = tokens.get("type", {})
    lines += [f"  --font-{key}: {stack};" for key, stack in type_.get("families", {}).items()]
    lines.append("}")
    if type_.get("fonts"):
        raise SyncError("tokens.json lists font files; add them to web/src/fonts.css and teach the generator")
    for group in type_.get("groups", []):
        for style in group["styles"]:
            family = style.get("family", group["family"])
            declarations = [f"font-family: var(--font-{family})"]
            declarations += [f"{css}: {_type_value(key, style[key])}" for key, css in _TYPE_PROPERTIES.items() if key in style]
            lines.append(f".{style['name']} {{ {'; '.join(declarations)}; }}")
    return "\n".join(lines) + "\n"


def bundle_css(source: str) -> str:
    return HEADER + _GOOGLE_FONTS_IMPORT.sub("", source)


def bundle_types(source: str) -> str:
    return HEADER + source


def check_namespace(bundle_js: str) -> None:
    match = re.match(r"/\* @ds-bundle: (\{.*?\}) \*/", bundle_js)
    namespace = json.loads(match.group(1))["namespace"] if match else None
    if namespace != NAMESPACE:
        raise SyncError(f"bundle.js namespace is {namespace!r}; web/src/thermal/index.ts expects {NAMESPACE!r}")


def generated_files(mirror: Path = MIRROR) -> dict[str, str]:
    components = mirror / "components"
    check_namespace((components / "bundle.js").read_text())
    return {
        "tokens.css": tokens_css(json.loads((mirror / "tokens.json").read_text())),
        "bundle.css": bundle_css((components / "bundle.css").read_text()),
        "thermal.d.ts": bundle_types((components / "index.d.ts").read_text()),
    }


def replace_mirror(source: Path) -> None:
    for required in ("tokens.json", "components/bundle.js", "components/bundle.css", "components/index.d.ts"):
        if not (source / required).is_file():
            raise SyncError(f"{source} has no {required}; pass the downloaded project/ folder")
    shutil.rmtree(MIRROR, ignore_errors=True)
    shutil.copytree(source, MIRROR)


def stale_files() -> list[str]:
    return [name for name, text in generated_files().items()
            if not (GENERATED / name).is_file() or (GENERATED / name).read_text() != text]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", nargs="?", type=Path, help="downloaded project/ folder of the artifact")
    parser.add_argument("--check", action="store_true", help="only report stale generated files")
    args = parser.parse_args()
    try:
        if args.check:
            stale = stale_files()
            if stale:
                sys.exit(f"Stale in {GENERATED.relative_to(ROOT)}: {', '.join(stale)}. Run sync_design_system.py.")
            print("Generated files are up to date.")
            return
        if args.source:
            replace_mirror(args.source.resolve())
            print(f"Mirrored {args.source} -> {MIRROR.relative_to(ROOT)}/")
        GENERATED.mkdir(parents=True, exist_ok=True)
        for name, text in generated_files().items():
            (GENERATED / name).write_text(text)
            print(f"Wrote {(GENERATED / name).relative_to(ROOT)}")
    except SyncError as error:
        sys.exit(f"ERROR: {error}")


if __name__ == "__main__":
    main()
