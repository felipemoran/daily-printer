# Feature: `photo_print` CLI

Prints a photo on the thermal printer. Entry point: `src/scripts/photo_print.py`. Dithering lives in `src/photo_dither.py`.

## Workflow

1. Pick a method on screen: `make photo-compare PHOTO=me.jpg`. This writes a sheet with every method. It never prints.
2. Judge on paper: `make photo-strip PHOTO=me.jpg`. This prints a 16 mm band of the photo per method.
3. Print the photo: `uv run src/scripts/photo_print.py me.jpg --method atkinson --gamma 1.4`.

Previews go to `artifacts/photo-<utc>/`. That directory is gitignored.

## Options

| Flag | Default | Effect |
|---|---|---|
| `--method` | `atkinson` | `atkinson`, `floyd-steinberg`, `jarvis`, `stucki`, `bayer`, `threshold` |
| `--gamma` | `1.3` | Midtone lift. Raise it if faces print muddy. |
| `--sharpen` | `100` | Unsharp-mask percent. `0` disables it. |
| `--contrast-cutoff` | `1.0` | Autocontrast clip percent. `0` disables it. |
| `--erode` | off | Trim the bottom dot of vertical runs to offset heat smear (see `feature-page-print.md`). |
| `--erode-min-run` | `3` | Only trim runs at least this tall. |
| `--compare` / `--test-strip` | off | Screen sheet / paper strip of every method. |
| `--no-print` | off | Write previews only. |

## Thermal-paper quirks

- **Dot gain.** Printed dots bleed, so paper comes out darker than the preview. `--gamma` compensates. Only a paper test can tune it.
- **HEIC.** Pillow cannot read iPhone HEIC files. Convert first: `sips -s format jpeg IMG.HEIC --out IMG.jpg`.
- **Transport.** Print images over USB. BLE garbles rasters; see `setup-bluetooth-investigation.md`.
