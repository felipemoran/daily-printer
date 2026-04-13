# Receipt UI (Vite + React)

Thermal-width (**384 px**) receipt layout. All on-screen content comes from **`payload.json`** (no wall-clock reads in the UI for business data — timestamps are fields in JSON).

## Prerequisites

- Node.js + npm
- For headless capture from the repo root: Python deps via `uv` and Playwright’s browser:

  ```bash
  uv sync
  uv run playwright install chromium
  ```

## Develop

```bash
cd web
npm install
npm run dev
```

Edit **`public/payload.json`** (or replace it) while iterating. Vite serves it at `/payload.json`.

## Build (required before `receipt_print`)

`npm run build` needs dependencies first (`node_modules`). If you use **`--build`** from the Python CLI, run **`npm install` in `web/` once** (or after pulling).

```bash
cd web
npm install
npm run build
```

Output: **`dist/`** (gitignored from repo root via `dist/` rule). The Python CLI copies your run’s JSON to **`dist/payload.json`** before screenshotting.

## Print pipeline

From the **repository root**:

```bash
uv run python src/scripts/receipt_print.py samples/receipt-sample.json --no-print
```

Omit `--no-print` to send raster output to the printer (USB preferred, BLE fallback — see `src/printer.py`).

Artifacts (default under `artifacts/<utc>/`): `payload.json`, `receipt.png`, `preview.txt`.

Payload shape: see **`samples/receipt-sample.json`** and `schemaVersion` in `src/receiptPayload.ts`.
