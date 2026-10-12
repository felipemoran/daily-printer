# Feature: `page_print` CLI

`src/scripts/page_print.py` renders any folder with an `index.html` and a `#receipt` element in headless Chromium, converts it to 1-bit, and prints it. It is the tool for paper A/B tests; `--help` lists every flag. How the defaults were chosen: `research-print-quality.md`.

## Defaults

Settings come from `print_profile.DEFAULT_PROFILE`, the same profile `daily_print.py` and `receipt_print.py` use. Each flag overrides one setting. `--legacy` starts from the pre-2026-10 profile instead.

| Flag | Default | Effect |
|---|---|---|
| `--page DIR` or `FILE.html` | `samples/photo-page` | Folder to render, or one HTML file served with its folder; `web/dist` renders the receipt app, `web/dist/thermal.html` the Thermal example |
| `--dither page/photo/none` | `page` | Dither the whole render; only the `--photo`; or threshold at 200 |
| `--method` | `atkinson` | Dithering method; `all` prints one page per method |
| `--anti-aliased-text` | off | Keep text anti-aliasing (default: aliased 1-bit glyphs) |
| `--weight normal/bold/faux-bold/auto` | `auto` | `auto`: bold below 18.5 px, regular above, for 2-dot stems. Thermal pages keep their CSS weights; the printed label still says `weight auto` |
| `--font`, `--font-file` | page fonts | Override every font; `--font-file` serves a font that is not installed |
| `--font-scale` | `1.0` | Multiply font sizes; sizes round to whole pixels (except `--legacy` at 1.0) |
| `--no-halo` | off | Skip the black outline around light text |
| `--page-gamma` | `1.0` | Tone curve before whole-page dithering; below 1 darkens |
| `--no-erode`, `--erode-min-run` | erode, `3` | Bottom-edge erosion against heat smear |
| `--photo`, `--gamma`, `--sharpen`, `--contrast-cutoff`, `--black-point`, `--white-point` | none, `1.3`, `100`, `1.0`, `0`, `255` | Photo for `img[data-photo]` and its tone |
| `--no-label` | off | Skip the settings line printed above each page (use it for keepsakes) |
| `--no-print`, `--artifact-dir` | print, `artifacts/page-<utc>` | Dry run and output folder |

## Pages with a photo

The page needs one `<img data-photo src="photo.png">` inside a `[data-photo-slot]` block. `page_print` measures the slot, prepares the photo at exactly that width, and snaps the image onto whole pixels before the screenshot. With `--dither photo` it also checks that render plus threshold changed no photo pixel, and refuses to print otherwise.

## Rules for pages

- Keep the `#receipt` element 384 px wide.
- Put text on solid black or white. Text on a dithered grey gets lost; the halo only helps a little.
- Make faint elements (soft shadows, grey text) darker in CSS than they look right on screen.
- Prefer sizes and weights whose stems measure 2 dots: `src/scripts/experiments/font_metrics.py`.
