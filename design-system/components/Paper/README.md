# Paper

The 58 mm strip: a 448px-wide white column with 32px margins around the 384-dot printable area, and the 56px tear feed at the end. Wrap every receipt in it.

- Provide: `children` (the receipt, top to bottom), `feed={false}` to drop the bottom feed when showing a fragment, `print` for print mode.
- **Print mode** (`print`): renders exactly the 384-dot raster as `<div id="receipt">`: no margins, shadow or desk colour, which would otherwise reach the pipeline as greys. Use one print-mode Paper per page.
- Text smoothing is off inside Paper (`-webkit-font-smoothing: none`) so the screen shows the same aliased glyphs the pipeline captures. Honoured by Chromium on macOS; other platforms untested.
- The screen shows structure only. Tone and weight are judged on paper.
- Do: design at 1 CSS px = 1 dot, whole-pixel sizes and line heights. Don't: scale the strip, or put anything wider than 384px inside it.
