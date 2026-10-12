# TestType

Paper test for text weight per size (items 2, 14, 15 of the To verify list). Pair it with `font_metrics.py`, which measures stem width in dots, characters per line and x-height for the same font, size and weight.

- IBM Plex Mono at 14, 15, 16, 18, 20, 21 and 22px in 400, 500, 600 and 700; reversed (paper on ink) at 16, 18 and 20px in 500 and 700; Archivo condensed at the display sizes in 700 and 900.
- Look for: the faintest weight that still prints solid at each size (target 2-dot stems); whether 14px bold is legible; whether reversed 500 fills in; where 900 display strokes smear.
- Result decides the weights of the Mono type styles and the 14px floor.
