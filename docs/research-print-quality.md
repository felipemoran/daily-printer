# Research: print quality on the MPT-II thermal printer

Record of the print-quality tests run on 2026-09-30 and 2026-10-01. It keeps every test, including partial and abandoned ones, so a future change of printer, paper, app or taste starts from what is known instead of rediscovering it.

## Read first

- **Preferences are not facts.** One person judged every print by eye, at a desk, on one roll of paper. The owner's taste changed during the tests (see E19). Re-judge on paper when the printer, the paper, the content or the taste changes.
- **Every print went over the USB cable.** Bluetooth printed text but garbled every image, and the owner chose not to investigate further (E2). No finding below was checked over Bluetooth.
- **The screen lies about darkness.** Printed dots bleed into their neighbours (dot gain), so paper is always darker than a preview. Screen previews only show structure. Only paper decides tone.
- **Status of each experiment:**
  - **Concluded**: a pick was made on paper.
  - **Partial**: some results, no final pick.
  - **Not tested**: an idea or a hypothesis only.
  - **Reversed**: a pick that a later preference overruled.

### What probably transfers to another printer

| Probably general | Specific to this printer, paper or taste |
|---|---|
| One CSS pixel = one dot needs a 384 px viewport at device scale 1, and images on whole-pixel coordinates (E3) | How dark the dot gain is |
| Thresholding anti-aliased text at 200 fattens it; dithering it thins it (E5) | The heat smear below strokes, and that the firmware ignores `ESC 7` (E9) |
| Aliased text plus whole-page dithering leaves glyphs untouched (E5, E6) | The best erosion run length (E11) |
| 1-dot strokes print faint; stroke width matters more than any other text setting (E7, E15) | Tahoma 16 px bold as the favourite (E16) |
| Text on a dithered mid-tone gets lost (E4, E12) | The photo tone choice (E19) |
| Error diffusion beats ordered dithering for photos (E1) | Bluetooth garbling images (E2) |

## Setup

| Item | Value |
|---|---|
| Printer | MPT-II by YAEN, USB `0x6868:0x0200`, ESC/POS, firmware 1.0 |
| Resolution | 203 DPI, 384 dots across, 48 mm print width, 8 dots per mm |
| Paper | Standard 58 mm thermal roll |
| Transport | USB cable for every print |
| Renderer | Headless Chromium from Playwright 1.58.0 (browser build `chromium-1243`) on macOS |
| Libraries | python-escpos 3.1, Pillow 12.2.0 |
| Web build | Node from nvm (v24.13.0). On 2026-10-01 the Homebrew `node` failed to start: it could not load `libllhttp.9.3.dylib`. |
| Judging | Labelled paper prints compared side by side. The label is a printer-font line with the settings. |

## Current picks

These are the defaults since 2026-10-01. Code home: `src/print_profile.py` (`DEFAULT_PROFILE`), `web/src/App.css` and `src/photo_dither.py` (`prepare` defaults).

| Setting | Value | Experiment |
|---|---|---|
| Receipt font | Tahoma, Verdana as fallback. Tahoma is a macOS/Windows system font. | E16 |
| Receipt sizes | 18 px base (`12px * --receipt-scale`). Task text 18 px bold, section headers 19 px regular, date 27 px regular, meta lines 15 px bold. | E17, E18 |
| Weight | Automatic: bold below 18.5 px, regular from 18.5 px, so stems are 2 dots | E15 |
| Text anti-aliasing | Off (`-webkit-font-smoothing: none`), in the app CSS and at capture | E5, E6 |
| Light text | 1-dot black outline (halo) | E12 |
| Font sizes | Rounded to whole pixels at capture | E15 |
| 1-bit conversion | Whole-page Atkinson dithering | E3, E4 |
| Heat compensation | Erosion: drop the bottom dot of vertical black runs 3 or more dots tall | E9, E11 |
| Feed speed | Full USB speed | E10 |
| Photo tone | gamma 1.3, autocontrast clip 1%, full tone range (black 0, white 255), unsharp mask 100% | E19 |
| Photo layout | Full bleed: 384 dots wide, edge to edge | E19 |

`--legacy` on `daily_print.py`, `receipt_print.py` and `page_print.py` restores the pre-2026-10 raster: anti-aliased text, threshold at 200, no erosion. It does not restore the old font; that lives in `App.css`.

## Experiments

Commands use today's flags. Each one names the script that re-runs it.

### E1. Dithering algorithm for photos (Concluded)

- **Question:** which algorithm makes photos look best?
- **Setup:** `photo_print.py --compare` (screen sheet), then `--test-strip` (paper, one band per method). Lenna test image at full width.
- **Result:**
  - Threshold and Bayer: discarded. Threshold loses the face. Bayer's crosshatch fights faces.
  - Floyd-Steinberg, Jarvis, Stucki and Atkinson: close at 203 DPI. They differ mostly in grain.
  - Atkinson: slightly ahead. It drops 2/8 of the error, which gives clean highlights and solid shadows.
- **Pick:** Atkinson.

### E2. Bluetooth vs USB for images (Partial, abandoned by choice)

- **Question:** can images print over Bluetooth Low Energy (BLE)?
- **Results:**
  - Text over BLE: works.
  - Image, unpaced (about 7 KB/s): good for 1-2 lines, then garbage.
  - Image, paced at 800 B/s (`fix(printer): pace BLE writes`): printed slowly and well for a while, then garbage. The printer then printed "Hexadecimal Dump", followed by 50-70 lines of hex, until it was switched off.
  - The same image over USB: clean.
- **Reading:** bytes went missing. The printer left the image command early and read pixels as commands, until a byte pattern matched `GS ( A`, the test print in hex dump mode. At 800 B/s the printer was starved (printing slowly), so a full buffer does not explain that run.
- **Not tested:** the hypothesis that the BLE-to-serial bridge uses XON/XOFF and swallows every `0x11` and `0x13` byte. Dithered rasters contain many of those bytes; text has few. Test: hex dump mode (hold FEED while powering on), send bytes `00` to `ff`, check whether `11` and `13` are missing. `src/scripts/experiments/ble_probe.py` logs what the printer sends back during a paced send; it never ran to completion.
- **Connection rule found:** if macOS holds a Classic Bluetooth link (System Settings shows MPT-II as Connected), the printer stops advertising over BLE and the scan fails. Click Disconnect, not Forget. Details: `setup-bluetooth-investigation.md`.
- **Open decision:** `printer.py` paces BLE at 800 B/s since this test. It did not fix images and slows BLE text.

### E3. Page plus photo: whole-page dither vs photo-only dither (Concluded)

- **Question:** can the web pipeline print photos, and where should dithering happen?
- **Setup:** `samples/photo-page` with Lenna. `page_print.py --dither page` (all six methods) vs `--dither photo` (photo pre-dithered at its exact size, page thresholded).
- **Results:**
  - 1:1 check: the photo landed at y = 115.75. The line heights above it summed to a fraction. Chromium then resampled the photo and changed 33% of its dithered pixels.
  - Fix: snap images to whole pixels before the screenshot (`capture_receipt(snap_selector=...)`). After the fix, 0 of 111,556 pixels changed.
  - First snap attempt: used margins. Margin collapsing swallowed the nudge when the image followed a paragraph. The final version uses relative offsets.
  - Photo-only mode: text bolder and crisper, but too bold.
  - Whole-page mode: text weight more appropriate, but some strokes faint.
- **Pick:** whole-page dithering, with aliased text (E6) to fix the faint strokes.
- **Re-run:** `page_print.py --photo <photo> --dither photo`; `tests/test_page_alignment.py` guards the 1:1 rule.

### E4. UI elements: threshold vs whole-page dither (Concluded)

- **Setup:** `samples/ui-elements` (gradient header, badges, progress bars, cards, chart, grey ramp, orb, stripes, text, emoji), `--dither none` vs `--dither page`.
- **Result:**
  - Threshold collapses every grey to black or nothing: the 75% bar, the light chart bar and the yellow badge vanish.
  - Dithering keeps all tones.
  - White text on mid-grey (badges) and on the gradient is hard to read in both.
- **Pick:** whole-page dithering.

### E5. Text rendering variants (Concluded, screen only)

- **Setup:** `src/scripts/experiments/text_render_lab.py` on the real receipt.
- **Result:**

| Variant | Effect after 1-bit conversion |
|---|---|
| Anti-aliased, threshold 200 (legacy) | Bold: every edge pixel at least about 20% covered turns black |
| Anti-aliased, threshold 128 | Lighter but uneven stroke widths |
| `--disable-font-subpixel-positioning` | No visible change |
| 2x supersample, box downscale | Same as default |
| `-webkit-font-smoothing: none` | Exactly 2 grey levels: Chromium draws 1-bit glyphs, crisp and true weight |

- **Pick:** aliased text. Headless Chromium on macOS honours the property. Linux Chromium ignores it, so there `launch_chromium` in `src/raster_capture.py` turns antialiasing off with `src/aliased-text.fonts.conf`. CI tests it on Linux (`AliasedTextTest`).

### E6. Aliased text plus whole-page dither vs anti-aliased (Concluded)

- **Result:**
  - Body text: very similar between the two.
  - Aliased text: thin white strokes on the gradient header vanish ("linear black to white" unreadable). Anti-aliased strokes were fatter and survived better.
- **Pick:** aliased, then fix weight separately (E13, E15).

### E7. Type specimen with system fonts (Concluded)

- **Setup:** `samples/type-specimen`: JetBrains Mono, Verdana, Monaco, Helvetica at 14/18/24/32 px regular and 14/18/24 px bold, printed in three pipelines next to the printer's own Font A.
- **Result:**
  - No font reached Font A's quality. Font A is a 12x24-dot bitmap font with 2-dot strokes, drawn for the head.
  - Best: Verdana, whole-page dither, aliased text.
  - Monaco has no bold cut; its bold rows render regular.

### E8. Pixel fonts (Concluded: not adopted)

- **Setup:** `samples/specimens/pixel-fonts`: Spleen (12x24 = Font A's cell, 6x12, 8x16), Departure Mono (11 px grid), Cozette (6x13), only at native sizes or integer multiples.
- **Result:** crisp, but none matches Font A, and they look too utilitarian.

### E9. Heat smear below strokes (Concluded)

- **Observation:** a dark "shadow" under text, worst under large bold strokes. It appeared in prints with no dithering and aliased text, so the cause is the head, not the image. Each element is still hot from the previous dot row.
- **Setup:** `src/scripts/experiments/heat_tests.py --test esc7` and `--test erosion` on the Verdana block of the specimen.
- **Results:**
  - `ESC 7 n1 n2 n3` (heat dots, heat time, cooling interval): all strips identical, including their Font A labels. The firmware ignores it.
  - Erosion: sharper and lighter text.
- **Pick:** erosion, implemented as `photo_dither.erode_bottom_edges`.
- **Caution:** power-cycle the printer after `ESC 7` tests; the setting may persist until power-off.

### E10. Feed speed over USB (Concluded)

- **Setup:** `heat_tests.py --test feed`: the same bytes at full speed, 2000, 800 and 400 B/s.
- **Results:**
  - Pacing really slows printing: 2000 B/s slightly slower, 800 clearly slower, 400 far too slow.
  - Slower feeding lightens solid blacks: the black header bar paled at 800 and 400, and slightly at 2000.
  - 2000 B/s plus erosion: jagged; the solid header came out striped. Probably motor stop-start, not erosion. Erosion only touches the bottom edge of each black run.
  - 2000 B/s alone vs full speed plus erosion: 2000 won narrowly.
- **Pick:** full speed plus erosion, because speed matters to the owner.

### E11. Erosion minimum run length (Concluded)

- **Question:** erosion run >= 2 made dithered shades patchy. Does a longer minimum spare them?
- **Result:**
  - Run >= 3: shades less patchy; text still sharpened.
  - Run >= 4: no visible gain, and a little smearing back.
- **Pick:** run >= 3. Text stems are long runs; dither textures are mostly 1-2 dot runs.

### E12. Halo around light text (Concluded)

- **Setup:** `--no-halo` vs default; a 1-dot black outline drawn with CSS `text-shadow` on any element whose text colour is light.
- **Result:**
  - The gradient header text "pops", like something added on top rather than cut out.
  - Badges: slightly more readable.
  - "linear black to white": still unreadable at 13 px.
- **Pick:** keep.

### E13. Thicker text: bold, faux-bold, page gamma (Concluded)

- **Setup:**
  - `--weight bold` (every element 700).
  - `--weight faux-bold` (a copy shadowed 1 px right: every stem +1 dot).
  - `--page-gamma 0.8` (darkens light greys before dithering).
- **Results:**
  - All three improved on regular weight.
  - Page gamma lost detail in dark tones. Instead, darken faint elements (soft shadows, grey text) in the page CSS case by case.
  - Faux-bold: slightly darker, with smearing at the bottom of strokes.
  - Bold: slightly lighter and sharper.
- **Pick:** bold. Later refined to automatic weight (E15).
- **Rejected:** `-webkit-text-stroke`. It rounds unevenly on aliased text, giving a mix of 1-, 2- and 3-dot stems (measured).

### E14. Fonts with more weights (Concluded)

- **Options:**
  - Verdana Pro (Light to Black, plus condensed): commercial (Font Bureau/Monotype). It is free only through Windows' optional fonts, so it was not used.
  - Free variable fonts tested: Atkinson Hyperlegible Next and Inter (`samples/specimens/free-fonts`).
- **Result:** Inter on the UI page looks smaller, more compact and a little bolder. Verdana was still preferred.

### E15. Font size and the 2-dot stem rule (Concluded)

- **Setup:** `--font-scale 1.2` on Verdana bold.
- **Result:** too bold. Bold Verdana at 19 px has 4-dot stems.
- **Measurement:** `src/scripts/experiments/font_metrics.py`, aliased stem width in dots:

| Font | 16 px | 19 px | 22 px |
|---|---|---|---|
| Verdana | 400: 1 · 700: 2 | 400: 2 · 700: 4 | 400: 2 · 700: 4 |
| Tahoma | 400: 1 · 700: 2 | 400: 2 · 700: 3 | 400: 2 · 700: 4 |
| Avenir Next Condensed | 500: 1 · 600: 2 · 700: 2 | 500: 2 · 600: 2 · 700: 3 | 500: 2 · 600: 3 · 700: 3 |

- **Rule:** pick the weight per size so every stem is 2 dots, as in Font A. `--weight auto` does this for Verdana and Tahoma: bold below 18.5 px, regular from there. Other fonts need their own threshold. Measure first.

### E16. Narrower fonts (Concluded)

- **Measurement at 16 px** (`font_metrics.py`):

| Font | Characters per 384-dot line | x-height |
|---|---|---|
| Verdana bold | 43 | 8.8 px |
| Tahoma bold | 48 | 8.8 px |
| Avenir Next Condensed DemiBold | 65 | 8.2 px |
| Arial Narrow bold | 63 | 8.3 px |
| Trebuchet MS bold | 51 | 8.4 px |

- **Setup:** `samples/specimens/two-dot-stems`: only combinations that measured 2-dot stems, each with two receipt lines and a white-on-black line.
- **Pick:** Tahoma 16 px bold, "the best balance". Tahoma is Verdana's narrower sibling by the same designer.

### E17. The real receipt (Concluded)

- **Setup:** `page_print.py --page web/dist` on the 13 April receipt, legacy vs Tahoma with automatic weight, aliased text, halo, page dither and erosion, with fonts scaled x0.667, then x0.75.
- **Result:**
  - x0.667: 40% shorter than legacy, but too small.
  - x0.75: "perfect", and about 30% shorter than legacy.
- **Pick:** x0.75. Now the default.

### E18. Porting the pick into the app (Concluded)

- **Finding:** the approved print came from an older `web/dist` build. Its CSS used a 17 px design base with /17 ratios; the committed source used 16 px with /16.
- **Port:** a base of `12px * --receipt-scale` (18 px), plus section header `17em / 16` and meta lines `13em / 16`. This reproduces every font size and weight of the approved print. Spacing differs by about 1% (12 dots over 16 cm), from sub-pixel padding.

### E19. Photo tone for a keepsake (Reversed: back to defaults)

- **Photo:** a selfie of two people at a park, one in a near-black jacket.
- **Layout:** full bleed, date and a caption centred below, `text-wrap: balance` on the caption.
- **First print** (defaults: gamma 1.3, clip 1%): much darker than the screen. The jacket printed solid black. Faces looked washed out, on screen too.
- **Measured tones** on the 384-dot render: jacket median 52 of 255; faces median 224-228.
- **New controls:** `--black-point` and `--white-point` rescale tones into a range.
- **Paper rounds** (`src/scripts/experiments/tone_sweep.py`, three columns per strip, the same slice at print scale):

| Round | Fixed | Varied | Result |
|---|---|---|---|
| R1 | white 245, gamma 1.0 | black 32 / 64 / 96 | Face: 64 best (32 too dark, 96 featureless). Jacket: solid 32 looked best; 64 and 96 showed patches unrelated to the jacket. |
| R2 | white 245, gamma 1.0 | black 48 / 64 / 80, plus a second face | 64 |
| R3 | black 64, white 255 | gamma 1.0 / 1.1 / 1.2 | 1.1 |
| R4 | gamma 1.1, white 255 | black 32 / 48 / 64 | No verdict: paper ran out |

- **A second test photo** (three people, dark clothes) printed with gamma 1.0, no clip, range 48-216. No verdict recorded.
- **Final preference:** the first print's defaults. They give stronger contrast and deeper blacks, "the most stylish", without feeling mushy, despite washed-out faces and solid blacks. Defaults stay; the tone-range flags stay available.
- **Not tested:** whether erosion causes the jacket patches. Erosion trims tall runs, and lifted dark areas are full of them. Test: one strip, erosion on vs off (`tone_sweep.py --erode-min-run 0` vs `3`).

## Open questions

- **Bluetooth images:** test the XON/XOFF hypothesis (E2). Decide whether the 800 B/s BLE pacing stays.
- **Jacket patches:** erosion on vs off in lifted dark areas (E19).
- **Tone round R4:** never judged (E19).
- **Auto-weight thresholds for other fonts:** measure with `font_metrics.py` before using `--weight auto` with them.
- **Other renderers:** aliased text comes from `-webkit-font-smoothing` on macOS and from fontconfig on Linux (`launch_chromium`, E5). Windows not tested.
- **Not tried:**
  - pixel fonts at Font A size for receipt body text only;
  - Verdana Pro (needs a licence);
  - Atkinson Hyperlegible Next on the real receipt;
  - another paper brand;
  - print density through `DC2 # n`, a command some generic printers accept. Not checked on this one.

## Redo checklist for a new printer, paper or app

1. **Width:** confirm the dot width and set `PRINT_WIDTH_DOTS`. The capture viewport must equal it at device scale 1.
2. **Transport:** print text and one image over each transport. Use the one that prints images cleanly.
3. **Dithering:** run `photo_print.py --test-strip` on a photo with faces.
4. **Heat control:** run `heat_tests.py --test esc7`. If strips differ, head heat is controllable, and erosion may be unnecessary.
5. **Smear:** run `heat_tests.py --test erosion`, then tune the run length on a page with shades.
6. **Stems:** run `font_metrics.py` for candidate fonts. Find each font's size where bold turns from 2 to 3 dots. Set `AUTO_WEIGHT_MAX_BOLD_PX` per font.
7. **Fonts:** print `samples/specimens/two-dot-stems` (or a new specimen) next to the printer's own font.
8. **Real content:** A/B the real page: `page_print.py --page web/dist` vs `--legacy`.
9. **Photo tone:** round by round with `tone_sweep.py`: wide values first, then narrow.

## Tools

| Tool | Use |
|---|---|
| `src/scripts/page_print.py` | Render any page folder with the profile; `--legacy`, `--dither page/photo/none`, font and weight overrides, `--no-label` |
| `src/scripts/photo_print.py` | Photos: `--compare`, `--test-strip`, tone flags, `--erode` |
| `src/scripts/experiments/tone_sweep.py` | Side-by-side tone variants on one strip |
| `src/scripts/experiments/font_metrics.py` | Stem width, characters per line, x-height |
| `src/scripts/experiments/text_render_lab.py` | Text rendering variants on screen |
| `src/scripts/experiments/heat_tests.py` | `ESC 7`, feed-speed and erosion strips |
| `src/scripts/experiments/ble_probe.py` | BLE send with RX logging |
| `samples/` | Test pages; `samples/specimens/README.md` lists font downloads |
