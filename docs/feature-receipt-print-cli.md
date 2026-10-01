# Feature: `receipt_print` CLI

Python entrypoint: **`src/scripts/receipt_print.py`**. It takes a **JSON payload**, renders it with the **Vite + React** receipt app in **`web/dist/`**, captures a **PNG of the `#receipt` element** with **Playwright**, optionally converts to **1-bit** for thermal output, then sends **ESC/POS raster** to the printer (unless **`--no-print`**).

Related: **`web/README.md`** (UI dev/build), **`docs/planning-react-headless-raster-print.md`** (design), **`docs/README.md`** (all docs), **`samples/receipt-sample.json`** (payload shape).

---

## How to run

From anywhere (the script resolves the **repository root** from its own path):

```bash
cd /path/to/daily-printer
uv sync
uv run playwright install chromium    # once per machine / fresh venv

uv run python src/scripts/receipt_print.py <payload.json> [options]
```

**Help:**

```bash
uv run python src/scripts/receipt_print.py --help
```

---

## One-time setup

| Requirement | Notes |
|-------------|--------|
| **Python deps** | `uv sync` (includes `playwright`, `pillow`, `python-escpos`, …). |
| **Playwright Chromium** | `uv run playwright install chromium`. If missing, the tool raises a clear error pointing here. |
| **`web/dist/`** | Produced each run by **`npm run build`** in **`web/`** (default). Requires **`web/node_modules`** (`cd web && npm install` once). Pass **`--no-build`** to reuse an existing **`dist/`** without rebuilding. |

---

## Options

| Flag | Default | Effect |
|------|---------|--------|
| *(positional)* `payload_json` | — | Path to the receipt JSON file (must exist and parse as JSON). |
| `--artifact-dir DIR` | `artifacts/<UTC>/` e.g. `artifacts/20260413T120000Z` | Directory for **`payload.json`** (copy), **`receipt.png`**, **`preview.txt`**. Created if missing. |
| `--no-print` | off | **Only** write artifacts; do **not** open the printer. Use this for safe iteration. |
| `--no-build` | off | Skip **`npm run build`**; use whatever is already in **`web/dist/`** (faster when the UI is unchanged). |
| `--legacy` | off | Pre-2026-10 raster: anti-aliased text, threshold at 200, no erosion. Default: `print_profile.DEFAULT_PROFILE` (aliased text, automatic weight, halo, Atkinson dithering, erosion; see `research-print-quality.md`). |
| `--device-scale-factor N` | `1.0` | Playwright **`deviceScaleFactor`** (e.g. **`2`** for sharper screenshots; larger files / slower). |
| `--max-height-px N` | `4000` | Reserved for **vertical splitting** of long rasters; **`split_raster_vertical`** is still a **stub** (always one strip). |

**Printing (default):** With **`--no-print` omitted**, the script uses **`open_printer()`** in **`src/printer.py`** (USB if present, else BLE). Same requirements as other printer scripts (libusb, Bluetooth permissions, etc.).

---

## Payload JSON

- Shape matches **`samples/receipt-sample.json`** and **`web/src/receiptPayload.ts`** (`schemaVersion`, `title`, `generatedAt`, `lines`, …).
- The script only checks that the file is **valid JSON**; it does **not** validate the schema.
- **`generatedAt`** and any “clock” strings should be **fields in JSON** (the React UI does not use `Date` for business text).

---

## What each run does (order)

1. Resolve and validate **`payload_json`**.
2. Unless **`--no-build`**, run **`npm run build`** in **`web/`**.
3. Require **`web/dist/index.html`**.
4. Create **`artifact_dir`**; copy payload to **`artifact_dir/payload.json`** and **`web/dist/payload.json`** (**overwrites** the latter).
5. Start a short-lived **HTTP server** on **`127.0.0.1`** with a **random port**, serving **`web/dist/`**.
6. **Playwright** loads **`/index.html`**, waits for **`networkidle`**, **screenshot of `#receipt`** (height = laid-out content) → **`receipt.png`**.
7. **Pillow**: resize to **384 px** width (`PRINT_WIDTH_DOTS`), then 1-bit per the print profile → **`print.png`**.
8. **`split_raster_vertical`** (stub): one strip.
9. Unless **`--no-print`**, print each strip with **`p.image(...)`**, then **`ln(3)`** (no cut).

---

## Artifacts

| File | Contents |
|------|-----------|
| **`payload.json`** | Copy of the input payload (replay / audit). |
| **`receipt.png`** | RGBA/RGB screenshot as captured (before 1-bit conversion used for printing). |
| **`preview.txt`** | **`capture_url`** used during the run, path to saved payload, and **replay** hints. |
| **`print.png`** | The 1-bit image sent to the printer (written with `--no-print` too). |

---

## Quirks and important behavior

1. **`web/dist/payload.json` is overwritten** every run. Do not rely on it as a stable hand-edited file; keep sources elsewhere and pass them in as **`payload_json`**, or use **`web/public/payload.json`** only under **`npm run dev`**.
2. **Concurrent runs** can race on **`web/dist/payload.json`** if two processes overlap.
3. **`capture_url` in `preview.txt`** points at a server that **stops when the process exits**; reopening that URL later will fail unless you start your own static server (instructions are in **`preview.txt`**).
4. **Viewport** during capture is **384×720** logical pixels (initial window size only). The saved PNG is **cropped to `#receipt`**, so its height matches the receipt content — not the full viewport.
5. **Headless Chromium** is the reference renderer; output may differ slightly from Safari or desktop Chrome.
6. **Default is to print** — omitting **`--no-print`** will talk to hardware. For CI or laptops without the printer, always pass **`--no-print`** unless you intend to print.
7. **`--max-height-px`** does not split jobs yet; very tall receipts may stress memory or BLE payload size until splitting is implemented.
8. Older instructions may mention **`--build`**; the current interface is **build by default** with **`--no-build`** to skip. A hidden **`--build`** flag may still be accepted for compatibility but does nothing special.

---

## Troubleshooting

| Symptom | What to do |
|---------|------------|
| `web/dist/index.html missing` | `cd web && npm install`, then run the CLI again (build is default), or run **`npm run build`** manually. |
| `Missing web/node_modules` | `cd web && npm install` before running the CLI (build step needs it). |
| `npm not found` | Install Node.js / ensure **`npm`** is on **`PATH`**. |
| Playwright / executable / Chromium error | `uv run playwright install chromium`. |
| `screenshot failed` (timeout, etc.) | Payload too heavy, network from page, or broken **`/payload.json`** fetch — check **`web/dist`** contents and browser console under **`npm run dev`**. |
| Print errors | See **`src/printer.py`** and USB/BLE setup docs. |
