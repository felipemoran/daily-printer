---
id: 2026-10-12-8sz28a-integrate-the-design-system-session-s-work-workspa
title: Integrate the design-system session's work (workspace design-system__daily-printer) with the print system
status: done
priority: 2
created_date: 2026-10-12
dependencies:
- 2026-10-12-mwo0xv-server-device-hub-http-api-entry-point
labels: []
type: null
parent: 2026-10-12-6t1a04-print-system-server-devices-cli-web-form-simulatio
scope: null
phase: null
---

## Description

Operator request: merge the parallel design-system stream into this branch so the operator does not integrate by hand. Concurrent stream: join with a two-parent merge, then re-run gates. render_job.py depends on raster_capture.capture_receipt, print_profile (capture_options, load_gray, to_bitmap, join_js, DEFAULT_PROFILE), photo_dither (prepare, dither), and the web app contract (/payload.json, #receipt, .receipt--error).

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

- 2026-10-12T06:35:21+00:00: Proposed to design-system session: kind 'template', payload {template, schemaVersion, data}; their module (suggested src/ticket_templates.py) validates (single site) and renders to a 1-bit 384-wide PIL image via a page I own per worker thread; TemplateError -> 422; fail fast (error boundary, explicit timeouts, DOM height check before screenshot); I keep ESC/POS, queue, devices. Merge via two-parent merge after the server wave. Awaiting their reply.
- 2026-10-12T07:32:54+00:00: Design-system interim integration point: otvylkrs (empty merge, reviewed+gated). API unchanged; more TemplateError cases (payload > 64 KiB, field-named validation, text fit, paper edge, layout settling, 3 s in-page timeout). New npm dep qrcode-generator 2.0.4; src/web_build.py build_web(); print_profile.to_gray(); daily_print --template; samples/templates/<name>.json. Residual: a sync busy loop in a template could freeze page.evaluate (no current template can).
- 2026-10-12T07:56:45+00:00: Final-tip follow-up for my side: call ticket_templates.check_envelope(payload) before launching Chromium (rejects bad envelope, unknown template via dist/templates.json, >64 KiB UTF-8); add kind 'text' via render_text(page, payload) -> body bytes with the raster preview from render_template on the same page.
- 2026-10-12T08:08:14+00:00: Design-system stable point nrlvsnow: all 14 templates, gate green (187 tests x2), .receipt overflow-wrap fix. Plan: when the final tip arrives, re-parent my merge (oupows) onto it in one step (jj rebase -s <merge> -d <my line> -d <final tip>), then add check_envelope + kind 'text'. Final tip adds ServerFault mapping: template server-side failure -> RuntimeError (500), not TemplateError.
- 2026-10-12T08:19:02+00:00: Merged interim point otvylkrs (oupowsvyzunm) + template kind (novtrvuwvvkp), reviewed. Still in progress: final design-system tip (render_text, check_envelope, cm message), then re-parent the merge and add kind 'text'.
- 2026-10-12T09:00:23+00:00: Final tip txrwsrox (41ad51c6) received. Changed plan: merge it at the tip of the line (new merge) instead of re-parenting oupows, to avoid rewriting ~25 reviewed commits. Builder in .workspaces/ps-final.
- 2026-10-12T09:18:00+00:00: Design-system follow-up coming on top of txrwsrox: check_envelope maps RecursionError -> TemplateError; public ticket_templates.TEXT_FEED. On arrival: small merge + make render_job import TEXT_FEED (drop its own).
- 2026-10-12T09:25:43+00:00: Final tip merged as ysnuyvyotzwv + envelope check prqzmrksmuws + text kind nkollmomnunk + form heading wunnxullqrol; reviewed. Waiting: design-system follow-up (RecursionError in check_envelope, public TEXT_FEED).
- 2026-10-12T09:42:27+00:00: Done. Merges: oupowsvyzunm (otvylkrs), ysnuyvyotzwv (txrwsrox), vxmkvowsnvmw (ppokxpmr). Kinds template + text; check_envelope before Chromium (depth <= 32: page.evaluate hangs ~150 deep). All reviewed.

## Decisions

- 2026-10-12T06:38:10+00:00: Agreed with design-system session: src/ticket_templates.py — open_render_page(browser)->Page, render_template(page, payload, *, max_height_dots=4000)->Image('1',384w), TemplateError(ValueError), template_names(). Server adds kind 'template'. Text-mode 1h stays raster; native text (render_text -> bytes) is a later operator decision. Keep 'receipt' kind until operator decides Tasks template replaces it.
- 2026-10-12T06:47:00+00:00: Operator approved (via design-system session): native text kind 'text' later — render_text(payload)->body bytes only (I add INIT + ln(3)); preview/paper_mm from render_template of the same payload. Operator wants receipt kind kept alongside the Tasks template.
