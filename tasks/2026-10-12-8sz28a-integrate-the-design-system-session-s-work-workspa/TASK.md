---
id: 2026-10-12-8sz28a-integrate-the-design-system-session-s-work-workspa
title: Integrate the design-system session's work (workspace design-system__daily-printer) with the print system
status: pending
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

## Decisions

- 2026-10-12T06:38:10+00:00: Agreed with design-system session: src/ticket_templates.py — open_render_page(browser)->Page, render_template(page, payload, *, max_height_dots=4000)->Image('1',384w), TemplateError(ValueError), template_names(). Server adds kind 'template'. Text-mode 1h stays raster; native text (render_text -> bytes) is a later operator decision. Keep 'receipt' kind until operator decides Tasks template replaces it.
- 2026-10-12T06:47:00+00:00: Operator approved (via design-system session): native text kind 'text' later — render_text(payload)->body bytes only (I add INIT + ln(3)); preview/paper_mm from render_template of the same payload. Operator wants receipt kind kept alongside the Tasks template.
