# To verify

Things the system currently assumes that have not been checked on paper. Each line says what to check and how. When something is settled, update the tokens or rule and delete the line.

## Type

- **Weights per size (Plex Mono).** Current weights are by role (500 body, 700 labels), not measured. Measure stem width in dots with `font_metrics.py` at 14–22px in 400/500/600/700, print `TestType`, and pick the weight that gives 2-dot stems at each size.
- **Archivo display sizes.** Stem width and smear of 900 at 42–172px are unmeasured. `TestType`, `TestSolids`.
- **14px floor.** Is 14px bold legible? `TestType`.
- **Reversed text at 700.** Does paper-on-ink text close up at 500, and hold at 700? `TestType`.
- **Characters per line.** Count per font and size with `font_metrics.py`; templates assume Plex Mono at 18px fits about 35 characters.
- **Text smoothing off.** `-webkit-font-smoothing: none` is only known to work in Chromium on macOS.

## Strokes and geometry

- **Stroke scale under erosion.** Do 3px rules print as 2px, and do 2/3/4 stay distinct? Compare the current scale (2/3/4/6/8) with 2/4/6/9. `TestStrokes`.
- **Box edges in flex layouts.** Chromium snaps box edges to pixels, but this hasn't been checked on paper for text-sized flex items (leaders, transitions). Look for soft or doubled edges in the templates.

## Tones

- **Tone values.** Which 10% steps stay distinct after dithering and dot gain; whether `tone-15` survives or prints white; whether `tone-65` stays distinct from solid in 10–11px cells; whether three states read at a glance. `TestTones`.

## Solids

- **Large solids and heavy strokes.** Smear, striping at full speed, unevenness in bands of 8–120px, the header bar, reversed tiles, the Severity block. `TestSolids`.

## QR

- **Module size.** Which of 1–5 dots per module scans with a phone, and from how far. `TestQR`.
- **Erosion on QR.** Whether trimming runs of 3+ dots hurts scanning at 3+ dots per module.

## Text mode

- **Native commands.** Reverse (`GS B`), double size (`GS !`) and the code page that holds `█ ░` on the MPT-II.
- **Line spacing.** The printer's default line spacing in text mode; the preview assumes a 24-dot line.
