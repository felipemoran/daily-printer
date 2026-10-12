# Image

A picture placed on whole pixels at print width. The print pipeline does the dithering and tone; this component only sizes and places.

- Provide: `src`, `width` (default 384), `height` (else computed from the picture and rounded), `caption`, `alt`.
- Keep the picture's top edge on a whole pixel: everything above it uses whole-pixel line heights, so this holds inside Paper.
- Captions go above or below, never on the picture.
- Intentional addition: not in the source explorations; added because photos and memes are a stated print kind.
