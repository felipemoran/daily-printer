---
id: 2026-10-12-937kap-ticket-templates-on-the-thermal-design-system-orch
title: Ticket templates on the Thermal design system — orchestrator mission log
status: pending
priority: 1
created_date: 2026-10-12
dependencies: []
labels: []
type: null
parent: null
scope: null
phase: null
---

## Description

Operator goal (2026-10-12): implement the ticket types (named templates with typed data) on the Thermal design system, for the print-system session to integrate later. Coordinate the payload/render contract with the print-system session (print-system-daily-printer-65, workspace .workspaces/print-system__daily-printer). Design source: Receipt Set 1 (tickets 1a-1n, first of three iterations) in Claude Design project d7dceba5-0ce2-4464-ad5f-9ede879d70a7; only the first iteration is wanted. Iteration happens locally on the work Mac (full stack + USB printer); no freeform layout DSL.

## Acceptance check

<!-- AC:BEGIN -->
- [ ]
<!-- AC:END -->

## Planning

## Execution log

## Decisions

- 2026-10-12T06:36:04+00:00: decided: implement the 8 templates of the mirrored bundle now (operator said implement the bundle's ticket types if present); Receipt Set 1 (1a-1n) extends or replaces them when exported — easy to change
- 2026-10-12T06:36:04+00:00: Contract agreed with print-system session (2026-10-12): kind 'template', payload {template, schemaVersion, data}. Python API in src/ticket_templates.py: open_render_page(browser) -> Page, render_template(page, payload, *, max_height_dots) -> PIL Image mode '1', 384 wide, print profile applied; TemplateError(ValueError) for sender-fixable failures (unknown template, invalid data, render failure, too tall; mapped to HTTP 422); template_names(). Validation lives only here. Fail fast: React error boundary, explicit few-second timeouts, #receipt.offsetHeight > max_height_dots checked before the screenshot. Page reuse must leave no leftovers; a failed render leaves the page usable. Keep unchanged: raster_capture.capture_receipt; print_profile capture_options/load_gray/to_bitmap/join_js/DEFAULT_PROFILE; photo_dither prepare/dither; web app /payload.json, #receipt, .receipt--error.
- 2026-10-12T06:36:05+00:00: decided: no schema library yet (zod/ajv need operator approval); each template validates its data with small shared helpers and reports a field path — easy to change
- 2026-10-12T06:36:05+00:00: decided: QR codes are left out of templates until a QR generator library is approved; filed as a draft — easy to change
