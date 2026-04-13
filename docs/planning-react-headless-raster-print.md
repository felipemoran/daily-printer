# Planning: Component Web UI → Screenshot → POS (Headless)

## Status

**Planning — decisions incorporated (2026-04-13).** Next step is an **execution plan** (milestones, spike, boundaries); implementation only after that review.

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
- `docs/feature-preview.md` was a **sketch**; we may **replace** its Playwright-centric preview story if another tool is simpler. No obligation to extend that file as-is.

---

## Candidate features (in scope)

Early optimizations **out of scope** for now: partial rerenders, hard air-gapped/CDN requirements, and dedicated dark-paper theming (formerly sketched as extra feature rows — not pursued).

| ID | Feature | Notes |
|----|---------|--------|
| F1 | **Headless screenshot** | Load built page (e.g. `file://` or static server), capture **full-page or stitched** image without human interaction. |
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
| **feature-preview.md** | **Replace** the sketched approach if something else fits better. |
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

## Suggested next step

1. **Execution plan doc or section:** one vertical slice — **`web/`** Vite+React receipt at **384px**, gather step writes **`*.json`**, automation loads built page + JSON, **screenshot** → optional Pillow → ESC/POS → USB, with **configurable max height** and a **stub** for vertical **split** when over limit; emit **preview URL** + JSON (+ PNG) as optional artifacts.
2. Implement only after you sign off on that plan.

---

## Document meta

| Field | Value |
|-------|--------|
| Created | 2026-04-13 |
| Updated | 2026-04-13 (JSON contract, preview URL artifact, Vite+React locked) |
| Type | Planning / exploration |
| Related | `docs/feature-preview.md`, `docs/planning-phase-01-printer-research.md`, `AGENTS.md` |
