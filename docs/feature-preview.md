# Feature: Print Preview System

> **Note (2026-04):** The active direction for high-fidelity preview + print is the **Vite + React receipt** pipeline and **`src/scripts/receipt_print.py`** (see `docs/planning-react-headless-raster-print.md` and `web/README.md`). The renderer layout below is an earlier sketch and may be superseded.

## Goal

Produce a high-fidelity preview of the thermal print output **before** sending to the printer. Two output modes:

| Mode | Purpose | Audience |
|---|---|---|
| **Plain text** | Fast terminal check, AI-readable | Developer / automation |
| **HTML → PNG** | High-fidelity 48mm roll simulation | Visual iteration |

The system must be easy to extend for future content: rendered images, QR codes, barcodes, arbitrary HTML blocks, etc.

---

## Architecture

```
TaskSections
    │
    ▼
src/renderers/
    ├── base.py        AbstractRenderer — defines render(sections) → output
    ├── text.py        TextRenderer     — plain text to stdout / file
    ├── html.py        HtmlRenderer     — HTML string simulating thermal roll
    └── image.py       ImageRenderer    — HTML → PNG via Playwright (headless)

src/print_tasks.py     CLI: fetch tasks → choose renderer → output
src/escpos_renderer.py (future) sends ESC/POS bytes to printer
```

---

## Plain Text Renderer (`src/renderers/text.py`)

Outputs UTF-8 text. Two stub hooks for extensibility:

```python
class TextRenderer(AbstractRenderer):
    def render(self, sections: TaskSections) -> str: ...

    def output(self, text: str, *, file: Path | None = None) -> None:
        """Write to stdout or a file. Default: stdout."""
```

Format: section dividers (`───`), task lines, empty lines between tasks.
No color or escape codes — must be readable by an LLM or piped to a file.

---

## HTML Renderer (`src/renderers/html.py`)

Generates a self-contained HTML page that simulates a 48 mm thermal roll:

- **Width**: 384 px (1:1 mapping — 1 px = 1 dot)
- **Font**: monospace, ~12px (matching Font A character cell)
- **Colors**: black text on white/off-white (`#fafafa`) background
- **Margins**: 4 px left/right (matching physical paper margins)
- **Scroll**: page extends vertically as content grows

### Extension Points

The HTML template exposes a slot system so future content types plug in cleanly:

```python
# Conceptual interface
class HtmlBlock(Protocol):
    def to_html(self) -> str: ...

# Examples:
TextBlock("[ ] Task title\n    Apr 13  •  finance")
ImageBlock(path="qr.png", width=64)
DividerBlock()
RawHtmlBlock("<table>...</table>")  # arbitrary layouts
```

`HtmlRenderer.render(sections)` converts `TaskSections` into a list of `HtmlBlock`s and stitches them into the page template.

This means: if you generate a QR code PNG, wrap a rich HTML section, or paste a screenshot from another tool — it just becomes another `HtmlBlock`.

---

## Image Renderer (`src/renderers/image.py`)

Takes the HTML from `HtmlRenderer` and screenshots it to a PNG.

**Tool**: [Playwright](https://playwright.dev/python/) (headless Chromium).

```
uv add playwright
uv run playwright install chromium
```

```python
class ImageRenderer(AbstractRenderer):
    def render(self, sections: TaskSections) -> Path:
        html = HtmlRenderer().render(sections)
        # launch headless Chromium, set viewport to 384px wide,
        # screenshot full page → PNG
        return output_path  # e.g. /tmp/daily-print-preview.png
```

The PNG is then opened in the system viewer (`open preview.png` on macOS) or saved to a configurable path.

### Why Playwright

| Option | Pros | Cons |
|---|---|---|
| **Playwright** | Full CSS/JS, QR codes, images, any HTML layout | Requires Chromium download (~150 MB) |
| WeasyPrint | Lightweight, no browser | Limited CSS, no JS, tricky image support |
| Pillow | No extra deps | Manual pixel math, very hard to extend |

Playwright wins because the goal is **flexibility for future layouts**, not minimizing dependencies.

---

## CLI Entry Point (`src/print_tasks.py`)

```
uv run src/print_tasks.py --preview text     # plain text to terminal
uv run src/print_tasks.py --preview html     # open HTML in browser
uv run src/print_tasks.py --preview image    # render PNG, open in viewer
uv run src/print_tasks.py --print            # send to printer (future)
```

Default (no flags): `--preview text`.

---

## Implementation Plan

1. `src/renderers/base.py` — `AbstractRenderer` + `HtmlBlock` protocol
2. `src/renderers/text.py` — `TextRenderer` with `file=` stub
3. `src/renderers/html.py` — `HtmlRenderer` with block slot system + CSS template
4. `src/renderers/image.py` — `ImageRenderer` (Playwright screenshot)
5. `src/print_tasks.py` — CLI wiring (`argparse`)
6. `uv add playwright && uv run playwright install chromium`

Steps 3–4 can be done in parallel once step 1 is finalized.
