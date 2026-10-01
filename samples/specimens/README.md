# Font specimens

Pages from the 2026-10 font tests. Results: `docs/research-print-quality.md`.
Render one with `page_print`, for example:

```bash
uv run src/scripts/page_print.py --page samples/specimens/two-dot-stems
```

| Page | Fonts | Needs a download |
|---|---|---|
| `two-dot-stems/` | Verdana, Tahoma, Avenir Next Condensed at sizes and weights that measured 2-dot stems | no (macOS system fonts) |
| `pixel-fonts/` | Spleen, Departure Mono, Cozette at native and integer-multiple sizes | yes |
| `free-fonts/` | Atkinson Hyperlegible Next and Inter at weights 400-700, Verdana as reference | yes |
| `../type-specimen/` | JetBrains Mono, Verdana, Monaco, Helvetica, 14-32 px | no |

The `fonts/` folders are gitignored: these fonts were tested, not adopted.
Add one to the repo only with its license, under `web/public/fonts/`.

## Downloads (versions tested)

Run from the repo root.

```bash
# pixel-fonts/: Spleen 2.2.0 (BSD-2), Departure Mono 1.500 (SIL OFL), Cozette 1.30.0 (MIT)
d=samples/specimens/pixel-fonts/fonts/pixel; mkdir -p "$d"
curl -sSfL https://github.com/fcambus/spleen/releases/download/2.2.0/spleen-2.2.0.tar.gz \
  | tar -xz --strip-components=1 -C "$d" spleen-2.2.0/spleen-6x12.woff2 spleen-2.2.0/spleen-8x16.woff2 spleen-2.2.0/spleen-12x24.woff2
curl -sSfLo /tmp/departure.zip https://github.com/rektdeckard/departure-mono/releases/download/v1.500/DepartureMono-1.500.zip
unzip -joq /tmp/departure.zip 'DepartureMono-1.500/DepartureMono-Regular.woff2' -d "$d"
gh release download -R the-moonwitch/Cozette --pattern CozetteVector.ttf --pattern CozetteVectorBold.ttf -D "$d"

# free-fonts/: Inter 4.1 (SIL OFL), Atkinson Hyperlegible Next variable (SIL OFL)
d=samples/specimens/free-fonts/fonts/free; mkdir -p "$d"
gh release download v4.1 -R rsms/inter --pattern Inter-4.1.zip -D /tmp --clobber
unzip -joq /tmp/Inter-4.1.zip InterVariable.ttf -d "$d"
curl -sSfLo "$d/AtkinsonNext.ttf" "https://raw.githubusercontent.com/googlefonts/atkinson-hyperlegible-next/main/fonts/variable/AtkinsonHyperlegibleNext%5Bwght%5D.ttf"
```
