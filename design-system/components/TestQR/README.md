# TestQR

Paper test for QR module size under dot gain and erosion (item 10 of the To verify list). The same 29 × 29 code (version 3, error correction M, a 37-character GitHub PR URL) at 1, 2, 3, 4 and 5 dots per module, each with a 4-module quiet zone.

- Physical size per module: 1 dot = 0.125 mm. Code width without the quiet zone: 29 × module × 0.125 mm.
- Look for: which sizes scan with a phone, from how far, and how fast. Erosion trims dark runs of 3+ dots, which shortens modules at 3+ dots per module and runs of stacked modules at 1–2.
- Result decides the QRSlot default `module`.
