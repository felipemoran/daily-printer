# QRSlot

A QR code that links the paper back to the screen, with up to three lines of context beside it.

- Provide: `matrix` (the code's modules as an array of `"1"`/`"0"` strings, from any QR encoder) with `module` (dots per module, default 3) and `quiet` (quiet-zone modules, default 4); or `src` (an image) with `size`; and `lines`.
- `matrix` is drawn on whole dots. The usable module size is untested: TestQR prints 1–5 dots per module.
- Without `matrix` or `src` it shows a `tone-15` placeholder slot.
