---
id: 2026-10-12-e111u3-native-esc-pos-text-output-for-1h-render-text-byte
title: Native ESC/POS text output for 1h (render_text -> bytes)
status: done
priority: 3
created_date: 2026-10-12
dependencies: []
labels: []
type: null
parent: 2026-10-12-937kap-ticket-templates-on-the-thermal-design-system-orch
scope: null
phase: null
---

## Description

Operator approved (2026-10-12) as a lower-priority fallback print path, to do near the end. render_text(payload) -> bytes: native Font A text, 32 columns, double size and reverse via ESC/POS. New job kind on the print server; coordinate with the print-system session.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T06:47:54+00:00: Agreed with print-system session: kind 'text', same envelope as 'template'. render_text returns the BODY only (no INIT, no trailing feed, no cut); reset any double size, reverse or alignment it sets. The server also calls render_template on 1h for the preview image and paper length, so the raster 1h must keep the same line breaks as the text bytes.
- 2026-10-12T07:46:46+00:00: From 1h review: send ESC 3 24 (the preview assumes a 24-dot line; default spacing is ~30 dots, so paper length from the raster would be short); some firmware auto-wraps at column 32 AND feeds on LF — a full 32-char rule may print a blank line (unverified on MPT-II). Output charset = printable ASCII + CP437 █ (0xDB) ░ (0xB0). buildLines needs a window.templateLines(payload) export in render-main.
- 2026-10-12T07:54:00+00:00: Also (from the print-system review): make raster_capture._ALIASED_TEXT_CSS a public name and import it; replace render_template's bitmap.convert('1') fallback (Pillow would Floyd-Steinberg dither, not the paper-tested profile) with a RuntimeError if to_bitmap ever returns another mode.
- 2026-10-12T07:56:40+00:00: Also (print-system review): payload size counts UTF-8 bytes (json.dumps(ensure_ascii=False).encode()), not ASCII-escaped; public check_envelope(payload) raising TemplateError for envelope + size BEFORE a browser is launched (schema checks still need the page); too-tall message in cm ('would print 51.3 cm long; the limit is 50 cm').
- 2026-10-12T08:03:02+00:00: Also: a font that fails to load (focus.tsx, agenda.tsx) must reach render_template's caller as a server fault (RuntimeError), not TemplateError: tag the error in render-main and map it in ticket_templates.py.
- 2026-10-12T08:09:21+00:00: Built rssqpw: render_text(page, payload) -> bytes; check_envelope(payload); cm message; RuntimeError for non-'1' bitmaps; public ALIASED_TEXT_CSS; ServerFault mapping; window.templateLines; tests (test_render_text 4, test_ticket_templates 29). Unverified on hardware: code page 0 for █ ░, ESC 3 24 spacing, GS B / GS ! on this firmware, column-32 auto-wrap. In review; will add print_template.py --text for local paper checks.
- 2026-10-12T08:12:15+00:00: Review of rssqpw: bytes and line-break proof sound. 🔴 no production ServerFault producer — closed by tkunlq (faults.ts) once integrated; needs an end-to-end test (fonts.load rejected → RuntimeError). 🟡 envelope tests need dist; template lookup order; stale page / line-model invariant / TypeErrors map to 422; Chinese double-byte mode (FS &) would garble █ ░ pairs. Fix round on the combined integration: tests skip without dist, lookup last, typeof check + invert rule in templateLines (only data/envelope errors are sender faults), send FS . at start, named constants, print_template.py --text for local paper checks.
- 2026-10-12T08:13:14+00:00: Integrated rssqpw in merge zspqqk; fix round next in .workspaces/tpl-text2 on zspqqk.
- 2026-10-12T08:17:47+00:00: Fix round: mmoyyq (end-to-end ServerFault tests; envelope tests without dist; lookup last; inverted fault rule in templateLines; FS . first; named constants; print_template.py --text). Re-review sent.
- 2026-10-12T08:18:58+00:00: Re-review: approved. Nits sent (rename local serverFault, timer order, parse TypeError → server fault on the raster path too). Told the print server to reopen the page after a RuntimeError.
- 2026-10-12T08:20:06+00:00: Nits: zmqqsn (prefixed(), timer order, shared parseData: any non-validation parse throw is a server fault on both paths). Final tip zmqqsn.

## Decisions

- 2026-10-12T07:54:07+00:00: Agreed with the print-system session: render_text(page, payload) -> bytes (page passed in; same page used for the preview raster). Body only (no INIT, no trailing feed, no cut), printer state reset at the end, line breaks identical to the 1h raster.
- 2026-10-12T08:12:15+00:00: decided: render_text sends FS . (cancel Chinese double-byte mode) at the start — harmless where unsupported, required on many generic printers; the body cannot restore an unknown FS & state, which no raster job depends on — easy to change
