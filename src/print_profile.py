"""Print profile: every render and raster setting picked on paper, in one place.

Findings and how they were chosen: docs/research-print-quality.md.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image

from photo_dither import dither, erode_bottom_edges
from printer import PRINT_WIDTH_DOTS

# Shadows are pixel-exact on aliased text. Faux-bold: a 1px-right copy turns
# 1-dot stems into 2-dot stems. Halo: a 1-dot black outline keeps light text
# from merging into dithered or heat-smeared dark backgrounds. text-shadow is
# inherited, so dark text nested in haloed text is reset to none unless it
# sets its own shadow. Colours go
# through a canvas pixel because computed colours can stay in oklch() or color().
_TEXT_EFFECTS_JS = """
() => {
  const HALO = %(halo)s, FAUX_BOLD = %(faux_bold)s;
  const probe = document.createElement('canvas').getContext('2d', { willReadFrequently: true });
  const luminance = (color) => {
    probe.clearRect(0, 0, 1, 1);
    probe.fillStyle = color;
    probe.fillRect(0, 0, 1, 1);
    const [r, g, b, a] = probe.getImageData(0, 0, 1, 1).data;
    return a === 0 ? 0 : (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  };
  for (const el of document.querySelectorAll('#receipt, #receipt *')) {
    const hasText = [...el.childNodes].some((n) => n.nodeType === Node.TEXT_NODE && n.textContent.trim());
    if (!hasText) continue;
    const color = getComputedStyle(el).color;
    const shadows = FAUX_BOLD ? [`1px 0 0 ${color}`] : [];
    if (HALO && luminance(color) > 0.6) {
      for (let x = -1; x <= (FAUX_BOLD ? 2 : 1); x++)
        for (let y = -1; y <= 1; y++)
          if (x || y) shadows.push(`${x}px ${y}px 0 #000`);
    }
    if (shadows.length > (FAUX_BOLD ? 1 : 0)) el.dataset.printHalo = '';
    if (shadows.length) el.style.textShadow = shadows.join(', ');
    else if (el.parentElement && el.parentElement.closest('[data-print-halo]')
             && getComputedStyle(el).textShadow === getComputedStyle(el.parentElement).textShadow)
      el.style.textShadow = 'none';
  }
}
"""


# Read every computed size first, then write: scaling while walking would
# compound through inheritance. Whole pixels keep aliased glyphs even.
_FONT_SCALE_JS = """
() => {
  const SCALE = %(scale)s;
  const sized = [...document.querySelectorAll('#receipt, #receipt *')].map((el) => {
    const style = getComputedStyle(el);
    return [el, parseFloat(style.fontSize), style.lineHeight];
  });
  for (const [el, size, lineHeight] of sized) {
    el.style.fontSize = `${Math.round(size * SCALE)}px`;
    if (lineHeight.endsWith('px')) el.style.lineHeight = `${Math.round(parseFloat(lineHeight) * SCALE)}px`;
  }
}
"""


# Measured on aliased Verdana and Tahoma: bold gives 2-dot stems up to ~18px,
# regular gives 2-dot stems from ~19px; past that bold reaches 3-4 dots.
AUTO_WEIGHT_MAX_BOLD_PX = 18.5
_AUTO_WEIGHT_JS = """
() => {
  // Thermal pages (design-system/) set the weight per size themselves.
  if (document.querySelector('#receipt.rp-paper')) return;
  const sized = [...document.querySelectorAll('#receipt, #receipt *')]
    .map((el) => [el, parseFloat(getComputedStyle(el).fontSize)]);
  for (const [el, size] of sized) el.style.fontWeight = size < %(max_bold)s ? '700' : '400';
}
"""


def auto_weight_js() -> str:
    return _AUTO_WEIGHT_JS % {"max_bold": AUTO_WEIGHT_MAX_BOLD_PX}


def text_effects_js(*, halo: bool, faux_bold: bool) -> str | None:
    if not (halo or faux_bold):
        return None
    return _TEXT_EFFECTS_JS % {"halo": str(halo).lower(), "faux_bold": str(faux_bold).lower()}


def join_js(*scripts: str | None) -> str | None:
    bodies = [script.strip() for script in scripts if script]
    if not bodies:
        return None
    return "() => {\n" + "\n".join(f"({body})();" for body in bodies) + "\n}"


@dataclass(frozen=True)
class PrintProfile:
    dither: str = "page"  # "page": dither the whole render; "none": threshold at 200
    method: str = "atkinson"
    aliased_text: bool = True
    light_text_halo: bool = True
    weight: str = "auto"  # normal | bold | faux-bold | auto
    font: str | None = None
    font_file: Path | None = None
    font_scale: float = 1.0
    snap_font_sizes: bool = True
    page_gamma: float = 1.0
    erode_min_run: int | None = 3  # None disables erosion

    def with_(self, **changes) -> "PrintProfile":
        return replace(self, **changes)


DEFAULT_PROFILE = PrintProfile()
# The raster pipeline before 2026-10: anti-aliased text, threshold, no extras.
LEGACY_PROFILE = PrintProfile(
    dither="none",
    aliased_text=False,
    light_text_halo=False,
    weight="normal",
    snap_font_sizes=False,
    erode_min_run=None,
)


def _css_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def capture_options(profile: PrintProfile) -> dict:
    """Keyword arguments for ``raster_capture.capture_receipt``."""
    css = []
    if not profile.aliased_text:
        # Pages may turn smoothing off themselves (the receipt app does).
        css.append("#receipt, #receipt * { -webkit-font-smoothing: antialiased !important; }")
    if profile.font_file:
        css.append(
            f"@font-face {{ font-family: {_css_string(profile.font)}; "
            f"src: url('/fonts/override/{profile.font_file.name}'); font-weight: 100 900; }}"
        )
    if profile.font:
        css.append(f"#receipt, #receipt * {{ font-family: {_css_string(profile.font)} !important; }}")
    if profile.weight == "bold":
        css.append("#receipt, #receipt * { font-weight: 700 !important; }")
    scale = profile.font_scale if (profile.font_scale != 1.0 or profile.snap_font_sizes) else None
    return {
        "aliased_text": profile.aliased_text,
        "extra_css": "\n".join(css) or None,
        "prepare_js": join_js(
            _FONT_SCALE_JS % {"scale": scale} if scale else None,
            auto_weight_js() if profile.weight == "auto" else None,
            text_effects_js(halo=profile.light_text_halo, faux_bold=profile.weight == "faux-bold"),
        ),
    }


def load_gray(screenshot: Path) -> Image.Image:
    """Screenshot as grayscale, alpha flattened on white, ``PRINT_WIDTH_DOTS`` wide."""
    image = Image.open(screenshot).convert("RGBA")
    flat = Image.new("RGBA", image.size, (255, 255, 255, 255))
    gray = Image.alpha_composite(flat, image).convert("L")
    if gray.width != PRINT_WIDTH_DOTS:
        height = max(1, round(gray.height * PRINT_WIDTH_DOTS / gray.width))
        gray = gray.resize((PRINT_WIDTH_DOTS, height), Image.Resampling.LANCZOS)
    return gray


def threshold(gray: Image.Image) -> Image.Image:
    return gray.point(lambda value: 255 if value > 200 else 0, mode="1")


def to_bitmap(gray: Image.Image, profile: PrintProfile, *, method: str | None = None) -> Image.Image:
    """Dither or threshold a grayscale render, then erode, per ``profile``."""
    if profile.dither == "page":
        if profile.page_gamma != 1.0:
            gray = gray.point([round(255 * (v / 255) ** (1 / profile.page_gamma)) for v in range(256)])
        bitmap = dither(gray, method or profile.method)
    else:
        bitmap = threshold(gray)
    return erode(bitmap, profile)


def erode(bitmap: Image.Image, profile: PrintProfile) -> Image.Image:
    if profile.erode_min_run is None:
        return bitmap
    return erode_bottom_edges(bitmap, min_run=profile.erode_min_run)


def describe(profile: PrintProfile) -> str:
    """Short label printed above test prints."""
    parts = [
        f"dither {profile.method}" if profile.dither == "page" else "threshold",
        profile.font or "page fonts",
        "aliased" if profile.aliased_text else "anti-aliased",
    ]
    if profile.weight != "normal":
        parts.append(f"weight {profile.weight}")
    if profile.font_scale != 1.0:
        parts.append(f"fonts x{profile.font_scale}")
    if profile.light_text_halo:
        parts.append("halo")
    if profile.page_gamma != 1.0 and profile.dither == "page":
        parts.append(f"page gamma {profile.page_gamma}")
    parts.append("no erosion" if profile.erode_min_run is None else f"erosion run>={profile.erode_min_run}")
    return ", ".join(parts)
