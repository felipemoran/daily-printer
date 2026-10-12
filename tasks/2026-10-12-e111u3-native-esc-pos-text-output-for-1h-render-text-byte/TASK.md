---
id: 2026-10-12-e111u3-native-esc-pos-text-output-for-1h-render-text-byte
title: Native ESC/POS text output for 1h (render_text -> bytes)
status: pending
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

## Decisions
