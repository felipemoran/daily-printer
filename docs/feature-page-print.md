# Feature: `page_print` CLI and rendering findings

`src/scripts/page_print.py` renders any folder with an `index.html` and a `#receipt` element in headless Chromium, converts it to 1-bit, and prints it. Run `--help` for every flag. Samples: `samples/photo-page`, `samples/ui-elements`, `samples/type-specimen`. It also renders the built receipt app: `--page web/dist`.

## Best settings so far

Picked on paper on 2026-10-01, on the 13 April receipt and the UI sample:

```bash
uv run src/scripts/page_print.py --page web/dist --dither page --aliased-text \
  --light-text-halo --font Tahoma --weight auto --font-scale 0.75
```

The receipt app itself still uses JetBrains Mono at a 24 px base. These flags override it at capture time; porting them into `web/src/App.css` and `receipt_print.py` is not done.

## Findings

| Lever | Finding |
|---|---|
| 1:1 pixels | The 384 px viewport maps one CSS pixel to one dot horizontally. Text line heights leave later elements at fractional y, and Chromium then resamples images there (33% of a dithered photo's pixels changed). `capture_receipt(snap_selector=...)` nudges images onto whole pixels with relative offsets; margins collapse into neighbours and do not work. |
| Threshold > 200 | Fattens text: any pixel at least ~20% covered prints black. Too bold. |
| Whole-page dithering | Keeps every grey (gradients, shadows, photos). Thins anti-aliased text. |
| Aliased text (`-webkit-font-smoothing: none`) | Honoured by headless Chromium on macOS: glyphs render 1-bit, so dithering leaves them untouched. Best with whole-page dithering. |
| Stem width | The single biggest factor. The printer's Font A uses 2-dot strokes. 1-dot strokes print faint; 3-4-dot strokes look heavy. Aliased Verdana and Tahoma: bold gives 2-dot stems up to ~18 px, regular from ~19 px. `--weight auto` applies that rule. `-webkit-text-stroke` rounds unevenly (mixed 1-3 dot stems). |
| Fonts tried | Tahoma 16 px bold won. Verdana is wider (12% fewer characters per line). Inter is compact but heavier. JetBrains Mono, Monaco, Helvetica, and the pixel fonts Spleen, Departure Mono, and Cozette all lost; the pixel fonts looked too utilitarian. |
| Text on mid-tones | White text on a dithered grey gets lost. `--light-text-halo` (1-dot black outline) helps; solid black backgrounds solve it. Darken faint shades (soft shadows, grey text) in the page CSS; a global `--page-gamma` below 1 lost dark-tone detail. |
| Heat smear | The head is still hot from the previous row, so a dark smear trails below strokes. `ESC 7` heat parameters are ignored by this firmware. Feeding data slowly over USB reduces smear but fades solid blacks and can band. Erosion (`photo_dither.erode_bottom_edges`, default run >= 3) trims the bottom dot of tall vertical runs; run >= 2 made dithered shades patchy. |
