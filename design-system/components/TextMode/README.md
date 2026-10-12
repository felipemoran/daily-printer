# TextMode

A screen preview of a print sent as native ESC/POS text in the printer's built-in Font A (12 × 24-dot cell, 32 columns). The real output is text, not a raster: it is the best-quality type the printer has and the only kind that prints over Bluetooth.

- Provide: `lines`: strings (cut at 32 characters) or objects `{text, double?, reverse?}` (double size cuts at 16 characters). `{inverse: "TEXT"}` is shorthand for double and reversed.
- JetBrains Mono only stands in for Font A on screen. Never rasterize this component for print.
- Unverified on this printer: reverse (`GS B`) and double size (`GS !`), and which code page holds `█ ░`.
