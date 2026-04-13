# Planning: Component Web UI → Screenshot → POS (Headless)

## Status

**Execution plan:** initial implementation is in the repo (`web/`, `src/scripts/receipt_print.py`, `src/raster_capture.py`, etc.); treat the plan below as the checklist and evolve it as you iterate.

**Planning decisions** (JSON contract, Vite + React, screenshot-only, Mac-only, no CI) are incorporated above.

**Scope note:** Side hobby project — **keep it simple.** **No CI** for now; **Mac** is the target runtime (this or another machine). CI or a headless server may come later.

## Goal

- **End state:** Autonomously send **printed** content to the **58 mm ESC/POS** printer (384-dot width per existing calibration).
- **Capture model:** Use **viewport screenshot** (pixel rasterization in headless Chromium), **not** the system print path or “Save as PDF” — this is not a normal CUPS printer workflow.
- **Authoring:** **Vite + React** in monorepo **`web/`** — browser preview while developing, modules, reusable components (see [Chosen UI stack](#chosen-ui-stack)).
- **Nice-to-have:** If easy, persist **digital artifacts** (e.g. PNG and/or HTML snapshot) for debugging and casual historical lookup — secondary to printing.

## Data flow: JSON file → web render → bitmap

It should be possible to define **all input data** used to render the receipt web page with a **single JSON document** (schema to be defined at implementation time).

**Pipeline (logical steps):**

1. **Gather / generate** — whatever step fetches or computes tasks, calendar, etc. **writes one JSON file** that is the complete, explicit payload for the UI (aligned with [F4](#candidate-features-in-scope): no hidden wall-clock reads inside the UI layer; anything time-dependent is **fields inside that JSON**, produced by the gather step).
2. **Render** — the built **Vite + React** app reads that JSON and renders the receipt layout (headless Chromium screenshots the result for ESC/POS; same build opened in a normal browser for dev).
3. **Convert** — raster capture → optional Pillow processing → ESC/POS → printer.

**Preview URL artifact:** The automation should also be able to emit a **generated URL** that encodes or references the same state so you can **paste it into a browser** and immediately see the exact content that will be printed — useful for quick inspection without hunting for the JSON path. (Exact mechanism is implementation detail: e.g. `file:` + query, `data:` URL, hash-based payload, or a tiny local static server — see edge cases for URL size limits.)

This split keeps **data extraction** (Python) and **presentation** (React) loosely coupled and makes reruns and debugging easier: keep the JSON, tweak layout, re-screenshot.

## Repo context

- Python today: `python-escpos`, USB + BLE. The pipeline needs a clean step from **raster bytes** (or PNG) into existing printer code.
- **Operational docs:** [`docs/feature-receipt-print-cli.md`](feature-receipt-print-cli.md) and [`web/README.md`](../web/README.md). See [`docs/README.md`](README.md) for an index.

---

## Candidate features (in scope)

Early optimizations **out of scope** for now: partial rerenders, hard air-gapped/CDN requirements, and dedicated dark-paper theming (formerly sketched as extra feature rows — not pursued).

| ID | Feature | Notes |
|----|---------|--------|
| F1 | **Headless screenshot** | Load built page over loopback HTTP, capture the **`#receipt`** node as PNG without human interaction. |
| F2 | **Vite + React authoring** | Monorepo **`web/`** beside **`src/`**; static build consumed by headless capture. |
| F3 | **Fixed thermal width** | Layout width locked to **384 px** (1:1 with dots) plus documented margins. |
| F4 | **Deterministic render inputs** | All page-building functions as **pure** as practical; **no hidden `Date.now()`** — pass **time (and locale/TZ if needed)** as explicit arguments with the rest of the payload. Same inputs → same DOM for a given build. |
| F5 | **CLI (and later cron)** | On-demand **`uv run …`**; **cron** wired up later — not blocking first vertical slice. |
| F6 | **ESC/POS raster output** | Image → ESC/POS raster commands → USB (preferred) or BLE; both transports already exist in the repo. |
| F7 | **Single pipeline** | Same built page drives **dev browser preview** and **headless capture** (one source of truth). |
| F8 | **JSON-driven render** | Gather step outputs **one JSON file** with the full render payload; React renders from that file; supports reproducibility, inspection, and **generated preview URLs** (see [Data flow](#data-flow-json-file--web-render--bitmap)). |

---

## Edge cases

| Area | Edge case | Mitigation / note |
|------|-----------|------------------|
| **Layout** | Very long receipts | **Split the raster** (or capture in vertical chunks) once height exceeds safe limits — avoids huge single bitmaps and printer/BLE stress. Exact threshold TBD in implementation. |
| **Typography** | System fonts | **Document** the stack; accept **headless Chromium** as the reference. No custom web fonts required for v1. |
| **Graphics** | SVG, filters, blend modes | Keep layouts mostly **text, borders, boxes**; heavy effects may differ; prefer simple CSS. |
| **Color** | sRGB → thermal | **Dithering allowed** only if it stays **simple** (e.g. built-in resize/threshold in Pillow, or a single clear algorithm). Otherwise default to crisp threshold. |
| **Images** | Hi-DPI | Define **`deviceScaleFactor`** vs logical 384 px width explicitly when tuning sharpness. |
| **Content** | RTL, CJK, emoji | Acknowledged; defer special cases unless you need them early. |
| **Dynamic data** | Time / randomness | **Deterministic contract:** inject **clock and any randomness** from Python (or a single seed) into the page payload — no silent `new Date()` in components for “business” display without passing props. |
| **Network** | External assets | **Trust all data at render time** for this project; still avoid accidental CDN dependency if you want offline renders (soft guideline, not a hard “F9” feature). |
| **URLs** | Long JSON in query strings | Browsers and tools impose **URL length limits**; large payloads may need a **hash fragment**, **file path + query**, or **short id** mapping to the JSON file instead of inlining the whole document in the query. |
| **JSON** | Schema drift | Optional: validate JSON against a **versioned schema** so gather and UI fail loudly when mismatched. |
| **Security** | Untrusted HTML | Not a v1 requirement given trusted inputs; revisit if user-generated HTML ever appears. |
| **Printer** | BLE chunking | Large jobs may require **splitting** aligned with long-receipt image splits. |

---

## Concerns (updated)

1. **Bitmap tradeoff:** Flexible layout vs bandwidth/BLE time and slightly softer text than native ESC/POS fonts — acceptable for this use case.
2. **Screenshot-only:** Avoid mixing mental models with PDF/print CSS unless we add a separate track later.
3. **Headless Chromium weight:** Playwright or Puppeteer is still the **simplest** “real browser” option for hobby Mac use; accept the download size locally.
4. **Debugging:** When something looks wrong, save **PNG + optional HTML**, the **`*.json` payload**, the **preview URL** (if generated), and log **viewport / DPR** — cheap and high value.
5. **YAGNI:** No CI, no server deployment, no partial updates until pain appears.

---

## Decisions (your answers — locked for this doc)

| Topic | Decision |
|-------|-----------|
| **Primary outcome** | **Print to hardware**; optional digital artifact if easy. |
| **Capture** | **Screenshot** of rendered page, not system print/PDF. |
| **React in production render** | Browser during dev is for **editing/preview**; headless run loads the **built static assets** (no requirement for hydration in the automation path unless we choose it for convenience). |
| **Repo layout** | **Monorepo** `web/` + `src/`. |
| **Runtime** | **Mac** for now; CI/server later. |
| **Data trust** | **Trust all** merged at render time. |
| **Color** | **Dithering OK** if complexity stays low. |
| **Visual parity** | **Simplest:** treat **headless Chromium** as canonical; don’t chase Safari parity. |
| **Automation** | **CLI** first; **cron** later. |
| **Human in the loop** | **Fully unattended** print; optional artifacts for debug/history. |
| **Documents per run** | **Single continuous receipt** (no cut into multiple jobs). |
| **Max length** | **Configurable**; example target **50 cm** vertical — use config rather than hardcoding. |
| **Fonts** | **System fonts**, documented. |
| **Assets** | Mostly **text, borders, boxes**; images/QR as needed but not the default complexity. |
| **Transport** | **USB and BLE**, favor **USB**; reuse existing code paths. |
| **UI stack** | **Vite + React** (`web/`). |
| **Render input** | **One JSON file** per job: gather step writes it; React renders it; same data drives headless and browser preview. |
| **Preview artifact** | **Generated URL** (or equivalent) so the full printable state can be opened quickly in a browser — alongside JSON/PNG as optional artifacts. |

---

## Chosen UI stack

**Vite + React** in **`web/`**, producing a **static build** that headless Chromium loads for screenshots and that you open in a browser during development (`vite dev`).

Rationale: strong **HMR**, familiar **component** model, straightforward **`vite build` → `dist/`** handoff to Python automation, and a good fit for the **JSON-in → layout-out** contract above.

### Alternatives considered (not selected)

For a hobby project the extra options (Preact, Astro, Svelte, Vue, 11ty) mainly trade **bundle size** or **template-first** ergonomics against **ecosystem familiarity**. Those remain valid pivots if React ever feels heavy; no need to revisit unless pain appears.

---

## Tools (shortlist aligned with decisions)

| Layer | Tool | Role |
|-------|------|------|
| Browser automation | **Playwright** or **Puppeteer** | Screenshot API, headless Chromium; pick one — **simplest docs + maintenance** wins for a solo Mac setup. |
| UI build | **Vite + React** | Static `web/dist/` (or chosen output dir) for capture and dev preview. |
| Raster post-process | **Pillow** | Optional resize, grayscale, **simple dither** or threshold before ESC/POS. |
| Print | **`python-escpos`** | Raster commands over USB/BLE (existing). |

Print-to-PDF tools (Prince, wkhtmltopdf, WeasyPrint) are **deprioritized** for the primary path because you chose **screenshot**, not print CSS. They remain optional references if you ever add a PDF archive.

---

## Execution plan

### Vertical slice (definition of done)

One **`uv run …` command** (exact module path TBD) that, given a **path to a JSON payload file**:

1. Optionally writes that JSON into an **artifact directory** for the run (always keep a copy for replay).
2. Serves or injects the payload so the **built Vite + React app** renders a **384 px** wide receipt (height grows with content).
3. Uses **headless Chromium** (via **Playwright**, default choice for Python + screenshot) to capture a **full-page screenshot** (PNG).
4. Optionally runs **Pillow**: grayscale, simple threshold or light dither (config flag), producing a **1-bit-friendly** bitmap if we choose not to let `python-escpos` handle conversion — exact division TBD in code (keep one clear path in v1).
5. Sends **raster ESC/POS** to the printer using existing **`open_printer()`** / `python-escpos` patterns in `src/printer.py` (`PRINT_WIDTH_DOTS = 384`).
6. Writes artifacts under a configurable directory: at minimum **`payload.json`** (copy), **`receipt.png`**, and a **`preview.txt`** (or similar) containing a **preview URL** and any local server instructions.

**Stub (explicit):** Implement **`split_raster_vertical(image, max_height_px) -> list[Image]`** (or equivalent) that today may return a **single-element list** only; document the future behavior for long receipts so the call site exists before tuning thresholds.

**Out of scope for v1 slice:** real Todoist (or other) API gather — use a **checked-in sample JSON** and a tiny **“fake gather”** script or CLI flag that only copies/writes that file. **Cron** wiring. **CI**. **Safari parity**.

---

### Why Playwright (default)

- **Python-native** driver story (`playwright` PyPI + `playwright install chromium`) fits the existing **`uv`** workflow.
- **Full-page screenshot** API is straightforward; **Puppeteer** would pull Node as a second automation stack unless we shell out.

If install size or ergonomics disappoint, switching to **Puppeteer** or **Chromium CLI** is still compatible with this plan — only the capture module changes.

---

### Serving JSON to the static app (`file://` vs HTTP)

`file://` pages **cannot reliably `fetch()`** arbitrary JSON paths (browser security). For a **single vertical slice**, standardize on **loopback HTTP** for both **dev** and **headless** capture:

- **Headless:** Python starts (or reuses) a **minimal static file server** rooted at **`web/dist/`** (or runs Playwright **`page.route`** to fulfill `GET /payload.json` from bytes). Navigate to e.g. `http://127.0.0.1:<port>/index.html` (exact path depends on Vite output).
- **Dev:** `npm run dev` (Vite) as today; same query or path convention for loading payload (e.g. drop `payload.json` under `web/public/` during dev, or use a dev-only query param documented in `web/README.md`).

**Preview URL artifact:** Prefer URLs that **reference the payload** without exceeding browser limits — e.g. `http://127.0.0.1:<port>/…` plus **path to copied JSON** documented next to the URL, or **hash fragment** with base64 for small payloads. Record whatever format you implement in **`preview.txt`**.

---

### JSON payload (v1)

- Include **`schemaVersion`** (integer) at the top level so the React app can fail visibly on mismatch.
- Keep the first sample minimal: e.g. **`title`**, **`generatedAt`** (ISO string from gather step — **not** read from `Date` in UI for display), **`lines`** or **`blocks`** array for body text.
- **Gather step contract:** any clock, timezone, or locale-dependent strings are **fields in JSON**, produced by Python (or typed manually in the sample file).

Formal **JSON Schema** validation (Python + optional TS) is **optional** for v1; add when the shape stabilizes.

---

### Repository layout (target)

```
daily-printer/
├── web/                    # Vite + React (new)
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/                # Receipt layout, 384px root width
├── src/
│   ├── printer.py          # existing — reuse PRINT_WIDTH_DOTS, open_printer
│   └── …                   # new module(s) e.g. raster_capture.py, receipt_cli.py (names TBD)
├── artifacts/              # gitignored default output root (optional)
└── docs/
    └── planning-react-headless-raster-print.md
```

Document in **`web/README.md`**: how to build (`npm install`, `npm run build`), how the app loads JSON, and how Python expects **`web/dist/`** to exist before capture.

---

### Configuration (v1)

| Setting | Purpose | Default suggestion |
|---------|---------|---------------------|
| `max_receipt_height_px` | Cap before **split** logic kicks in (future) | Derive from **50 cm** at **8 dots/mm** → **4000 px** if 1 px = 1 dot vertically; confirm in code comment against physical roll. |
| `device_scale_factor` | Playwright DPR for sharpness | Start at **1** or **2**; tune against printer. |
| `artifact_dir` | Where JSON/PNG/preview text go | `./artifacts/<timestamp>/` or user path |
| `print_enabled` | Run printer vs capture-only | CLI flag **`--no-print`** for safe iteration |

---

### Python dependencies (additive)

- **`playwright`** (capture).
- **`pillow`** (post-process before ESC/POS; see `receipt_image.py`).

Use **`uv add playwright pillow`** (or optional dependency group **`[receipt-render]`** if you want a slimmer default install — your call at implementation time).

After adding Playwright, document **`playwright install chromium`** in `web/README.md` or root README.

---

### Milestones (implementation order)

| # | Milestone | Deliverable |
|---|-----------|-------------|
| M1 | **`web/` scaffold** | Vite + React app with root layout **384 px** wide, sample static layout, `npm run build` → `dist/`. |
| M2 | **JSON → UI** | React reads payload from agreed mechanism (HTTP `payload.json` or equivalent); render sample file; no headless yet. |
| M3 | **Capture module** | Python: serve `dist/` + write payload, Playwright screenshot of **`#receipt`** → `artifact_dir` PNG. |
| M4 | **Pillow hook** | Optional threshold/dither; single code path documented. |
| M5 | **ESC/POS send** | Wire PNG → raster commands → `open_printer()`; **`--no-print`** for testing. |
| M6 | **Split stub + preview URL** | `split_raster_vertical` stub; write **`preview.txt`** with URL + notes. |
| M7 | **Docs cleanup** | Done: superseded sketch removed; use **`docs/feature-receipt-print-cli.md`**, **`docs/README.md`**, **`web/README.md`**. |

M1–M3 can be a **spike PR/commit series**; M4–M6 complete the slice.

---

### Acceptance checks (manual, no CI)

- **Determinism:** Same JSON file + same build → **byte-identical PNG** (or document acceptable diffs if font rasterization varies slightly).
- **Width:** Screenshot content width matches **384 px** logical layout (verify in an image viewer).
- **Printer:** **`--no-print`** produces artifacts only; with print, a short sample outputs on hardware without error.
- **Preview URL:** Pasting the URL from **`preview.txt`** into Chrome shows the same receipt as the PNG (allowing for subpixel variance).

---

### Implementation notes

Follow **`AGENTS.md`**: **`jj`** for commits, **`uv`** for Python deps, **`npm`** in `web/` (documented in `web/README.md`).

---

## Document meta

| Field | Value |
|-------|--------|
| Created | 2026-04-13 |
| Updated | 2026-04-13 (v1 pipeline; docs index; removed superseded `feature-preview.md`) |
| Type | Planning + execution |
| Related | `docs/feature-receipt-print-cli.md`, `docs/README.md`, `docs/planning-phase-01-printer-research.md`, `AGENTS.md` |
